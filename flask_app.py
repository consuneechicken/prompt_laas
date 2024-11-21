from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
from datetime import datetime, timedelta
import requests
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
import io
from flask import render_template  # 상단에 추가

app = Flask(__name__)

# CORS 설정
CORS(app, resources={
    r"/*": {
        "origins": ["*"],  # 프론트엔드 도메인으로 나중에 변경
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
        "supports_credentials": True
    }
})

# 기존 루트 경로 수정
@app.route('/')
def home():
    return render_template('prompton.html')

# 업로드 폴더 설정
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 업로드된 파일이 저장될 디렉토리 설정``
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 허용할 파일 확장자 설정
ALLOWED_EXTENSIONS = {'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_document(collection_code: str, doc_id: str, api_key: str, project_code: str, text: str) -> requests.Response:
    url = f"https://api-laas.wanted.co.kr/api/document/{collection_code}/{doc_id}"
    headers = {
        "Content-Type": "application/json",
        "apiKey": api_key,
        "project": project_code
    }
    data = {
        "text": text
    }
    return requests.put(url, headers=headers, json=data)

def split_and_update(collection_code: str, base_doc_id: str, api_key: str, project_code: str, text: str, max_length: int = 1000):
    chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    
    results = []
    for i, chunk in enumerate(chunks):
        doc_id = str(i+1)
        response = update_document('EX1', doc_id, api_key, project_code, chunk)
        
        if response.status_code not in [200, 201]:
            print(f"Failed to update document with doc_id {doc_id}. Status code: {response.status_code}")
            print("Response text:", response.text)
            results.append({
                'doc_id': doc_id,
                'status': 'failed',
                'message': response.text
            })
        else:
            print(f"Document updated with doc_id {doc_id}.")
            results.append({
                'doc_id': doc_id,
                'status': 'success',
                'message': f"Document updated with doc_id {doc_id}"
            })
    return results

@app.route('/file_upload', methods=['POST'])
def file_upload():
    try:
        # 기존 파일들 제거
        upload_dir = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    print(f"파일 삭제됨: {filename}")
            except Exception as e:
                print(f"파일 삭제 중 오류 발생: {filename}, 오류: {str(e)}")

        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400
        
        # API 키와 프로젝트 코드 확인
        api_key = request.form.get('api_key')
        project_code = request.form.get('project_code')
        collection_code = request.form.get('collection_code', 'EX1')  # 기본값 설정
        
        if not api_key or not project_code:
            return jsonify({'error': 'API 키와 프로젝트 코드가 필요합니다.'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': '선택된 파일이 없습니다.'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 파일 내용 읽기
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # API로 내용 전송
            update_results = split_and_update(
                collection_code=collection_code,
                base_doc_id="1",
                api_key=api_key,
                project_code=project_code,
                text=file_content
            )
                
            return jsonify({
                'message': '파일이 성공적으로 업로드되고 API로 전송되었습니다.',
                'content': file_content,
                'update_results': update_results
            }), 200
        else:
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': '파일 업로드 중 오류가 발생했습니다.'}), 500

@app.route('/extract_keywords', methods=['POST'])
def extract_keywords():
    try:
        data = request.get_json()
        print(f"받은 topic_num 값: {data.get('topic_num')}") 
        
        # 1. 키워드 추출
        url = "https://api-laas.wanted.co.kr/api/preset/v2/chat/completions"
        headers = {
            "project": data['project_code'],
            "apiKey": data['api_key'],
            "Content-Type": "application/json; charset=utf-8"
        }
        
        api_data = {
            "hash": "9f2df95ae2b9f5df95ed24c78ed6cdf96050c715a4e3fe97f30387a99b7f6b6a",
            "params": {
                "subject": data['subject'],
                'topic_num': data['topic_num']
            }
        }
        print("API 요청 데이터:", json.dumps(api_data, ensure_ascii=False))

        response = requests.post(url, headers=headers, json=api_data)
        print(f"API 응답 상태 코드: {response.status_code}")
        response.raise_for_status()

        response_filter = response.json()['choices'][0]['message']['content']
        lines = response_filter.strip().splitlines()
        topics = []
        keywords = []

        for line in lines:
            if line.startswith("topic"):
                topics.append(line.split(": ", 1)[1].strip())
            elif line.startswith("keywords"):
                keywords.append(line.split(": ", 1)[1].strip())
        print(topics)
        print(keywords)
        
        # 2. 문제 생성
        workbook = []
        progress_data = []  # 진행 상황을 저장할 리스트

        print(f"\n총 {len(topics)}개의 주제에 대해 문제를 생성합니다...\n")

        for idx, (topic, keyword) in enumerate(zip(topics, keywords), 1):
            print(f"[{idx}/{len(topics)}] '{topic}' 주제의 문제 생성 시작...")
            
            problem_data = {
                "hash": "0651dea457b0d90919be25d0d195d5726bbc9b9977716def729361141a614d3d",
                "params": {
                    "subject": data['subject'],
                    "number": data['number'],
                    "type_problem": data['type'],
                    "level": data['level'],
                    'keywords': keyword,
                    'topic': topic
                },
                "messages": [{"role": "user", "content": f"{topic}와 {keyword}를 이용해서 문제 만들어줘"}]
            }

            problem_response = requests.post(url, headers=headers, json=problem_data)
            
            response_data = problem_response.json()
            # choices가 없거나 비어있는 경우 다음 반복으로 넘어감
            if not response_data.get('choices'):
                print(f"Warning: '{topic}' 주제에 대한 응답에 choices가 없습니다. 건너뜁니다.")
                continue
            
            print(response_data['choices'][0]['message']['content'])
            workbook.append(response_data['choices'][0]['message']['content'])

            # 진행 상황 저장
            progress_data.append({
                'current': idx,
                'total': len(topics),
                'subject': data['subject']
            })

       # 3. 문제, 답, 해설 분류
        all_questions = []
        all_answers = []
        all_explanations = []

        for entry in workbook:
            try:
                parts = entry.split("답:")
                if len(parts) != 2:
                    continue
                
                question = parts[0].strip()
                remaining = parts[1].split("해설:")
                if len(remaining) != 2:
                    continue
                
                answer = remaining[0].strip()
                explanation = remaining[1].strip()
                
                all_questions.append(question)
                all_answers.append(answer)
                all_explanations.append(explanation)
                
            except Exception as e:
                print(f"항목 처리 중 오류: {str(e)}")
                continue

        if not all_questions:
            return jsonify({'error': '문제를 생성할 수 없습니다.'}), 500

        print(f"\n=== 문제 분류 결과 ===")
        print(f"문제 수: {len(all_questions)}")
        print(f"답변 수: {len(all_answers)}")
        print(f"해설 수: {len(all_explanations)}")

        try:
            # PDF 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"{data['subject']}_{timestamp}.pdf"
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)

            # PDF 생성
            pdf_buffer = create_pdf(all_questions, all_answers, all_explanations)
            
            # 디렉토리 확인
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            # PDF 파일 저장
            with open(pdf_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            
            print(f"\nPDF 파일 생성 완료: {pdf_path}")
            print(f"파일 크기: {os.path.getsize(pdf_path)} bytes")

            # 파일 권한 설정
            os.chmod(pdf_path, 0o644)

            return jsonify({
                'message': '문제가 성공적으로 생성되었습니다.',
                'filename': pdf_filename,
                'files': {
                    'pdf': f'/download/{pdf_filename}'
                }
            })

        except Exception as e:
            print(f"\nPDF 생성 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'PDF 생성 중 오류가 발생했습니다.'}), 500

    except Exception as e:
        print(f"전체 처리 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': '문제 생성 중 오류가 발생했습니다.'}), 500
        

def create_pdf(questions, answers, explanations):
    print("\n=== PDF 생성 시작 ===")
    print(f"받은 문제 수: {len(questions)}")
    print(f"받은 답변 수: {len(answers)}")
    print(f"받은 해설 수: {len(explanations)}")

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    width, height = A4
    
    # 한글 폰트 등록
    font_path = "NanumSquareNeo-aLt.ttf"
    try:
        pdfmetrics.registerFont(TTFont('NanumSquare', font_path))
        font_name = 'NanumSquare'
        print("한글 폰트 등록 성공")
    except Exception as e:
        print(f"Warning: 한글 폰트 등록 실패: {str(e)}")
        font_name = 'Helvetica'
    
    def draw_wrapped_text(text, x, y, width, font_size=12):
        if not text:
            print(f"Warning: 빈 텍스트가 전달됨")
            return y
            
        p.setFont(font_name, font_size)
        
        # \\n을 \n으로 변환
        text = text.replace('\\n', '\n')
        paragraphs = text.split('\n')
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                y -= font_size + 4
                continue
                
            # 각 문단에 대해 너비에 맞게 줄바꿈 처리
            chars = list(paragraph.strip())
            lines = []
            current_line = []
            
            for char in chars:
                current_line.append(char)
                line = ''.join(current_line)
                if p.stringWidth(line, font_name, font_size) > width:
                    current_line.pop()
                    lines.append(''.join(current_line))
                    current_line = [char]
            
            if current_line:
                lines.append(''.join(current_line))
            
            # 각 줄 그리기
            for line in lines:
                p.drawString(x, y, line)
                y -= font_size + 4
            
            # 문단 사이 추가 간격
            y -= font_size
        
        return y
    
    y = height - 50
    
    # 제목
    y = draw_wrapped_text("생성된 문제", 50, y, width-100, 16)
    y -= 30
    
    # 문제 부분
    for i, question in enumerate(questions, 1):
        if y < 100:  # 페이지 넘김
            p.showPage()
            p.setFont(font_name, 12)  # 새 페이지에서 폰트 재설정
            y = height - 50
        
        # 문제 번호와 내용
        y = draw_wrapped_text(f"[문제 {i}]", 50, y, width-100)
        y -= 10
        y = draw_wrapped_text(question.strip(), 50, y, width-100)
        y -= 20
    
    # 새 페이지에서 답안 시작
    p.showPage()
    y = height - 50
    y = draw_wrapped_text("정답", 50, y, width-100, 16)
    y -= 30
    
    # 답안 부분
    for i, answer in enumerate(answers, 1):
        if y < 100:
            p.showPage()
            p.setFont(font_name, 12)
            y = height - 50
        
        y = draw_wrapped_text(f"{i}. {answer}", 50, y, width-100)
        y -= 20
    
    # 새 페이지에서 해설 시작
    p.showPage()
    y = height - 50
    y = draw_wrapped_text("해설", 50, y, width-100, 16)
    y -= 30
    
    # 해설 부분
    for i, explanation in enumerate(explanations, 1):
        if y < 100:
            p.showPage()
            p.setFont(font_name, 12)
            y = height - 50
        
        y = draw_wrapped_text(f"{i}번 해설:", 50, y, width-100)
        y -= 10
        y = draw_wrapped_text(explanation, 50, y, width-100)
        y -= 30
    
    p.save()
    buffer.seek(0)
    return buffer


# PDF 다운로드 엔드포인트 추가
@app.route('/download/<filename>')
def download_file(filename):
    try:
        print(f"\n=== 파일 다운로드 요청 ===")
        print(f"요청된 파일명: {filename}")
        
        # 파일 확장자 확인 및 처리
        if not filename.endswith('.pdf'):
            filename = f"{filename}.pdf"
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        print(f"전체 파일 경로: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"파일이 존재하지 않음: {file_path}")
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404
            
        print(f"파일 존재 확인됨, 다운로드 시작")
        
        try:
            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,  # 확장자가 포함된 파일명
                mimetype='application/pdf'
            )
        except Exception as e:
            print(f"파일 전송 중 오류: {str(e)}")
            raise
            
    except Exception as e:
        print(f"다운로드 처리 중 오류: {str(e)}")
        return jsonify({'error': f'파일 다운로드 오류: {str(e)}'}), 500
    