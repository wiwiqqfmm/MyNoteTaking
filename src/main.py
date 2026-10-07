import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from src.models.user import db
from src.routes.note import note_bp
from src.routes.user import user_bp

load_dotenv(os.path.join(ROOT_DIR, '.env'))

app = Flask(__name__, static_folder=str((Path(__file__).resolve().parent / 'static')))
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

# Enable CORS for all routes
CORS(app)

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(note_bp, url_prefix='/api')


def get_database_url():
    database_url = os.getenv('SUPABASE_DB_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
        return database_url

    # TEMPORARY FALLBACK ONLY: Vercel's filesystem is ephemeral, so SQLite is not persistent.
    # This keeps the app booting in serverless environments before a real Supabase/Postgres URL is configured.
    return 'sqlite:///:memory:'


app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

try:
    from translator import client
except Exception as exc:  # pragma: no cover - import is optional for preview builds
    client = None
    _translator_import_error = exc
else:
    _translator_import_error = None

MODEL_NAME = os.getenv('OPENROUTER_MODEL')
if not MODEL_NAME:
    raise RuntimeError(
        'Missing required environment variable: OPENROUTER_MODEL. ' \
        'Set it in your local .env or Vercel project settings.'
    )
if not os.getenv('OPENROUTER_API_KEY'):
    raise RuntimeError(
        'Missing required environment variable: OPENROUTER_API_KEY. ' \
        'Set it in your local .env or Vercel project settings.'
    )
if not os.getenv('OPENROUTER_BASE_URL'):
    raise RuntimeError(
        'Missing required environment variable: OPENROUTER_BASE_URL. ' \
        'Set it in your local .env or Vercel project settings.'
    )


def load_translation_prompt(target_language):
    prompt_path = ROOT_DIR / 'prompts' / 'translate_prompt.md'
    with open(prompt_path, 'r', encoding='utf-8') as prompt_file:
        prompt = prompt_file.read().strip()
    return prompt.format(target_language=target_language)


def parse_translation_response(content):
    text = (content or '').strip()
    if not text:
        raise ValueError('Empty response from translation API')

    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:].strip()

    parsed = json.loads(text)
    if isinstance(parsed, dict):
        translated_title = parsed.get('title', '')
        translated_content = parsed.get('content', '')
    else:
        raise ValueError('Translation API did not return JSON object')

    return {
        'title': translated_title,
        'content': translated_content
    }


def translate_note_text(title, content, target_language):
    if client is None:
        raise RuntimeError(
            'Unable to initialize OpenRouter client. ' \
            f'Original import error: {_translator_import_error}'
        )

    user_payload = {
        'title': title,
        'content': content
    }
    system_prompt = load_translation_prompt(target_language)
    user_prompt = (
        'Translate the following JSON object. Return valid JSON with exactly two keys: "title" and "content".\n'
        + json.dumps(user_payload, ensure_ascii=False)
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        temperature=0.3
    )

    return parse_translation_response(response.choices[0].message.content)


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200


@app.route('/api/translate', methods=['POST'])
def translate_note():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    target_language = (data.get('target_language') or 'Chinese').strip() or 'Chinese'

    if not title and not content:
        return jsonify({'error': 'Title or content is required for translation'}), 400

    try:
        translated = translate_note_text(title, content, target_language)
        return jsonify(translated)
    except Exception as exc:
        return jsonify({'error': f'Translation failed: {str(exc)}'}), 500


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return 'Static folder not configured', 404

    if path != '' and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)

    index_path = os.path.join(static_folder_path, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(static_folder_path, 'index.html')

    return 'index.html not found', 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
