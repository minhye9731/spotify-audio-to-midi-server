from flask import Flask, request, send_file, jsonify
from basic_pitch.inference import predict, Model
from basic_pitch import ICASSP_2022_MODEL_PATH
import tempfile
import os
import io
import traceback
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 모델을 서버 시작 시 한 번만 로드
print("🤖 Basic Pitch 모델 로딩 중...")
try:
    basic_pitch_model = Model(ICASSP_2022_MODEL_PATH)
    print("✅ 모델 로딩 완료!")
except Exception as e:
    print(f"❌ 모델 로딩 실패: {e}")
    basic_pitch_model = None
    
# WAV만 허용 (변환 과정 생략)
ALLOWED_EXTENSIONS = {'wav'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    """WAV 파일만 허용"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/health', methods=['GET'])
def health_check():
    """서버 상태 확인"""
    return jsonify({
        'status': 'healthy',
        'service': 'Basic Pitch MIDI Converter',
        'version': '2.0.0',
        'supported_formats': ['wav']
    })

@app.route('/convert', methods=['POST'])
def convert_audio():
    """WAV 오디오를 MIDI로 변환"""
    try:
        print("🎵 WAV 변환 요청 받음")
        
        # 파일 검증
        if 'file' not in request.files:
            print("❌ 파일이 요청에 없음")
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        if file.filename == '':
            print("❌ 파일명이 비어있음")
            return jsonify({'error': 'No file selected'}), 400
            
        print(f"📁 파일명: {file.filename}")
        print(f"📁 파일 타입: {file.content_type}")
        
        if not allowed_file(file.filename):
            error_msg = f'Unsupported file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'
            print(f"❌ {error_msg}")
            return jsonify({'error': error_msg, 'message': 'Please record in WAV format from your iOS app'}), 400
        
        # 파일 읽기 및 크기 확인
        file_content = file.read()
        file_size = len(file_content)
        print(f"📊 WAV 파일 크기: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
        
        if file_size > MAX_FILE_SIZE:
            print(f"❌ 파일 크기 초과: {file_size} > {MAX_FILE_SIZE}")
            return jsonify({'error': 'File too large (max 10MB)'}), 400
        if file_size == 0:
            print("❌ 빈 파일")
            return jsonify({'error': 'Empty file'}), 400
        
        # 임시 WAV 파일 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        print(f"💾 임시 파일 생성: {temp_file_path}")
        print(f"✅ 임시 파일 존재 확인: {os.path.exists(temp_file_path)}")
        
        try:
            # 모델 사용 가능 여부 확인
            if basic_pitch_model is None:
                print("❌ 모델이 로드되지 않음")
                return jsonify({
                    'error': 'Model not loaded',
                    'details': 'Basic Pitch model failed to initialize',
                    'suggestion': 'Server restart required'
                }), 500
                
            # Basic Pitch 변환 실행 (WAV는 직접 처리 가능)
            print("🎼 WAV → MIDI 변환 시작...")
            model_output, midi_data, note_events = predict(
                temp_file_path,
                basic_pitch_model
            )
            print(f"✅ 변환 완료!")
            print(f"📊 감지된 노트 수: {len(note_events)}")
            print(f"📊 모델 출력 타입: {type(model_output)}")
            print(f"📊 MIDI 데이터 타입: {type(midi_data)}")
            
            # MIDI 데이터를 메모리 버퍼로
            midi_buffer = io.BytesIO()
            midi_data.write(midi_buffer)
            midi_buffer.seek(0)
            
            print(f"🎹 MIDI 파일 크기: {len(midi_buffer.getvalue())} bytes")

            if midi_size == 0:
                print("❌ MIDI 파일이 비어있음")
                return jsonify({
                    'error': 'Generated MIDI file is empty',
                    'details': 'No musical content detected in the audio'
                }), 500
            
            print("🎉 변환 성공! 파일 전송 중...")
            return send_file(
                midi_buffer,
                mimetype='audio/midi',
                as_attachment=True,
                download_name='converted.mid'
            )
            
        except Exception as conversion_error:
            error_msg = str(conversion_error)
            error_trace = traceback.format_exc()
            print(f"❌ 변환 실패: {error_msg}")
            print(f"📋 상세 오류: {error_trace}")
            
            # 더 구체적인 에러 정보 제공
            if "memory" in error_msg.lower():
                return jsonify({
                    'error': 'Memory error during conversion',
                    'details': 'File too large or insufficient server memory',
                    'suggestion': 'Try a smaller audio file'
                }), 500
            elif "model" in error_msg.lower():
                return jsonify({
                    'error': 'Model loading failed',
                    'details': error_msg,
                    'suggestion': 'Server model initialization error'
                }), 500
            else:
                return jsonify({
                    'error': 'Conversion failed',
                    'details': error_msg,
                    'trace': error_trace
                }), 500
            
        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                print("🗑️ 임시 파일 삭제 완료")
            else:
                print("⚠️ 임시 파일이 이미 삭제되었거나 존재하지 않음")
                
    except Exception as e:
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"❌ 서버 오류: {error_msg}")
        print(f"📋 전체 오류 스택:")
        print(error_trace)
        return jsonify({
            'error': 'Server error',
            'details': error_msg,
            'trace': error_trace
        }), 500

@app.route('/', methods=['GET'])
def index():
    """기본 엔드포인트"""
    return jsonify({
        'message': 'Basic Pitch MIDI Converter API (WAV Only)',
        'supported_format': 'WAV',
        'endpoints': {
            'health': '/health',
            'convert': '/convert (POST with audio file)'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
