from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import requests
import re
import os

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Get RapidAPI Key from environment variable (you set this on Vercel)
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', '')


def extract_shortcode(url):
    """Extract shortcode from Instagram URL"""
    patterns = [
        r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        r'instagram\.com/p/([A-Za-z0-9_-]+)',
        r'instagram\.com/tv/([A-Za-z0-9_-]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_video_from_rapidapi(url):
    """Get video URL using RapidAPI"""
    try:
        api_url = "https://instagram-scraper-api2.p.rapidapi.com/v1/post_info"

        querystring = {"code_or_id_or_url": url}

        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com"
        }

        response = requests.get(api_url, headers=headers, params=querystring, timeout=15)
        response.raise_for_status()

        data = response.json()

        if data.get('data'):
            post_data = data['data']

            # Get video URL
            video_url = post_data.get('video_url')

            if video_url:
                return {
                    'video_url': video_url,
                    'username': post_data.get('owner', {}).get('username', 'Unknown'),
                    'caption': post_data.get('caption', {}).get('text', '')[:200],
                    'likes': post_data.get('like_count', 0)
                }

        return None

    except Exception as e:
        print(f"RapidAPI Error: {e}")
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/download', methods=['POST'])
def download_reel():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        shortcode = extract_shortcode(url)
        if not shortcode:
            return jsonify({'error': 'Invalid Instagram URL'}), 400

        result = get_video_from_rapidapi(url)

        if not result or not result.get('video_url'):
            return jsonify({'error': 'Could not download video. Make sure the post is public.'}), 400

        return jsonify({
            'success': True,
            'message': 'Reel downloaded successfully',
            'video_url': result['video_url'],
            'caption': result.get('caption', ''),
            'likes': result.get('likes', 0),
            'owner': result.get('username', 'Unknown'),
            'shortcode': shortcode,
            'date': ''
        })

    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/download-video/<shortcode>')
def download_video_file(shortcode):
    try:
        instagram_url = f"https://www.instagram.com/reel/{shortcode}/"
        result = get_video_from_rapidapi(instagram_url)

        if not result or not result.get('video_url'):
            return jsonify({'error': 'Could not download video'}), 400

        video_url = result['video_url']

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(video_url, stream=True, headers=headers, timeout=30)
        response.raise_for_status()

        filename = f"instagram_reel_{shortcode}.mp4"

        def generate():
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk

        return Response(
            stream_with_context(generate()),
            content_type='video/mp4',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': response.headers.get('content-length', ''),
                'Cache-Control': 'no-cache'
            }
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/info', methods=['POST'])
def get_reel_info():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        result = get_video_from_rapidapi(url)

        if not result:
            return jsonify({'error': 'Could not fetch video info'}), 400

        return jsonify({
            'success': True,
            'is_video': True,
            'caption': result.get('caption', ''),
            'likes': result.get('likes', 0),
            'comments': 0,
            'date': '',
            'owner_username': result.get('username', 'Unknown'),
            'video_url': result['video_url'],
            'video_duration': None
        })

    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True)
