from flask import Flask, request, jsonify, Response, stream_with_context, render_template
import yt_dlp
import re
import os
import requests  # Crucial for streaming the direct video URL
from flask_cors import CORS
import time  # <-- ADDED: For retry logic delays

# --- CONFIGURATION ---
# FIX: The template folder path is adjusted to find 'templates' outside the 'api' directory.
# We use os.path.dirname and os.path.abspath to ensure the path is correctly resolved.
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')
app = Flask(__name__, template_folder=template_dir)
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Range"],
        "expose_headers": ["Content-Range", "Accept-Ranges", "Content-Length", "Content-Disposition"]
    }
})


# ---------------------


def extract_shortcode(url):
    """Extract shortcode from Instagram URL with query parameters"""
    url = url.split('?')[0].rstrip('/')

    patterns = [
        r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        r'instagram\.com/reels/([A-Za-z0-9_-]+)',
        r'instagram\.com/p/([A-Za-z0-9_-]+)',
        r'instagram\.com/tv/([A-Za-z0-9_-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            shortcode = match.group(1)
            print(f"✓ Extracted shortcode: {shortcode}")
            return shortcode
    return None


def get_video_info_ytdlp(url):
    """
    Core function to get video info using yt-dlp to find the direct stream URL.
    Returns info dict or None on fatal failure.
    """
    try:
        clean_url = url.split('?')[0]

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'format': 'best[ext=mp4]/best',
            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

            if not info:
                return None

            video_url = None
            formats = info.get('formats', [])

            for fmt in reversed(formats):
                if fmt.get('ext') == 'mp4' and fmt.get('url'):
                    video_url = fmt['url']
                    break

            if not video_url:
                video_url = info.get('url')

            if not video_url:
                return None

            return {
                'video_url': video_url,
                'username': info.get('uploader', 'Unknown'),
                'title': info.get('title', 'Instagram Video'),
                'duration': info.get('duration', 0),
            }

    except Exception as e:
        # We catch the exception here and let the retries handle it higher up
        raise e


def get_video_info_with_retries(url, max_retries=3):
    """
    Attempts to get video info, retrying on failure due to temporary network or API issues.
    """
    for attempt in range(max_retries):
        try:
            result = get_video_info_ytdlp(url)
            if result and result.get('video_url'):
                print(f"✓ Info fetch succeeded on attempt {attempt + 1}")
                return result
        except Exception as e:
            print(f"✗ Info fetch failed on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                # Wait before the next retry (exponential backoff not needed, simple wait is fine)
                time.sleep(2 * (attempt + 1))
            else:
                # Last attempt failed
                print("✗ All info fetch attempts failed.")
                return None


@app.route('/')
def index():
    # Renders the client-side HTML/JS
    return render_template('index.html')


@app.route('/api/info', methods=['POST', 'OPTIONS'])
def get_reel_info():
    """API endpoint to get video info (used by the 'Get Info' button)"""
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url or 'instagram.com' not in url:
            return jsonify({'error': 'Please provide a valid Instagram URL'}), 400

        shortcode = extract_shortcode(url)
        if not shortcode:
            return jsonify({'error': 'Invalid Instagram URL format'}), 400

        # ⭐ USE THE RETRY FUNCTION HERE
        result = get_video_info_with_retries(url)

        if not result:
            return jsonify(
                {'error': 'Could not fetch video info after retries. Video may be private or unavailable.'}), 400

        return jsonify({
            'success': True,
            'owner_username': result.get('username', 'Unknown'),
            'shortcode': shortcode,
            'video_duration': result.get('duration', None),
            'title': result.get('title', 'Instagram Video')
        })

    except Exception as e:
        print(f"✗ Info error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/stream-video/<shortcode>', methods=['GET'])
def stream_video_file(shortcode):
    """
    FIXED ROUTE: Streams video directly from source URL.
    This prevents mobile client timeouts (pending -> fails).
    """
    instagram_url = f"https://www.instagram.com/reel/{shortcode}/"
    filename = f"instagram_reel_{shortcode}.mp4"

    try:
        # 1. Get the direct, temporary video URL (⭐ USING RETRIES HERE TOO)
        info = get_video_info_with_retries(instagram_url)
        if not info or not info.get('video_url'):
            # This returns the small JSON file that causes the tiny failed download
            print(f"✗ Failed to get video URL for streaming after all retries for {shortcode}.")
            return jsonify({'error': 'Failed to get video stream URL from Instagram (retried 3 times).'}), 404

        direct_video_url = info['video_url']

        # 2. Prepare request headers, crucially passing the client's Range header
        headers = {
            'User-Agent': request.headers.get('User-Agent',
                                              'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15'),
            'Range': request.headers.get('Range', '')
        }

        # 3. Start a streaming request to the direct video URL
        r = requests.get(direct_video_url, headers=headers, stream=True, timeout=300)

        if r.status_code not in (200, 206):
            print(f"✗ Failed to get direct video stream. Status: {r.status_code}")
            return jsonify({'error': f'Failed to stream video from source. Status: {r.status_code}'}), 500

        # 4. Generator to yield chunks
        def generate_stream():
            try:
                for chunk in r.iter_content(chunk_size=8192):
                    yield chunk
            finally:
                r.close()

        # 5. Construct the final streaming Response
        response_headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Accept-Ranges': r.headers.get('Accept-Ranges', 'bytes'),
            'Content-Length': r.headers.get('Content-Length'),
            'Content-Range': r.headers.get('Content-Range'),
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }

        response = Response(
            stream_with_context(generate_stream()),
            status=r.status_code,
            mimetype='video/mp4',
            headers=response_headers
        )

        return response

    except Exception as e:
        print(f"✗ Streaming Error: {str(e)}")
        return jsonify({'error': f'Download/Streaming failed: {str(e)}'}), 500


if __name__ == '__main__':
    print(f"\n{'=' * 70}")
    print(f"🚀 Flask Instagram Downloader - FIXED & STREAMING")
    print(f"✓ Streaming route: /api/stream-video/<shortcode>")
    print(f"{'=' * 70}\n")
    # In a production environment, use gunicorn: gunicorn -w 4 app:app
    app.run(debug=True, host='0.0.0.0', port=5000)
