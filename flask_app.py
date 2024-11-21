from flask import Flask, request, jsonify, send_from_directory, send_file, render_template
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
from datetime import datetime
import requests
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
import io

app = Flask(__name__)
CORS(app)

# 업로드 폴더 설정
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 허용할 파일 확장자 설정
ALLOWED_EXTENSIONS = {'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return render_template('prompton.html')

@app.route('/file_upload', methods=['POST'])
def file_upload():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400
        
        file = request.files['file']
        api_key = request.form.get('api_key')
        project_code = request.form.get('project_code')
        
        if not api_key or not project_code:
            return jsonify({'error': 'API 키와 프로젝트 코드가 필요합니다.'}), 400
        
        if file.filename == '':
            return jsonify({'error': '선택된 파일이 없습니다.'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            return jsonify({
                'message': '파일이 성공적으로 업로드되었습니다.',
                'content': file_content
            }), 200
        else:
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400
            
    except Exception as e:
        return jsonify({'error': f'파일 업로드 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/extract_keywords', methods=['POST'])
def extract_keywords():
    try:
        data = request.get_json()
        
        # API 요청
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

        response = requests.post(url, headers=headers, json=api_data)
        if not response.ok:
            return jsonify({'error': '키워드 추출 중 오류가 발생했습니다.'}), 400

        # PDF 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{data['subject']}_{timestamp}.pdf"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)

        # PDF 버퍼 생성
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.drawString(100, 750, "Generated Content")
        p.save()
        buffer.seek(0)

        with open(pdf_path, 'wb') as f:
            f.write(buffer.getvalue())

        return jsonify({
            'message': '문제가 생성되었습니다.',
            'filename': pdf_filename,
            'files': {
                'pdf': f'/download/{pdf_filename}'
            }
        })

    except Exception as e:
        return jsonify({'error': f'처리 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'파일 다운로드 오류: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)