from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file
import yt_dlp
import re
import os
import tempfile
import json
import requests  # <-- ADDED: For streaming the direct video URL
import shutil
from werkzeug.utils import secure_filename
from flask_cors import CORS

# --- CONFIGURATION ---
# IMPORTANT: When deploying, set FLASK_ENV=production and use a proper WSGI server (Gunicorn)
app = Flask(__name__, template_folder='../templates', static_folder='../static')
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
    Get video info using yt-dlp to find the direct stream URL.
    """
    try:
        print(f"\n{'=' * 70}")
        print(f"Fetching: {url}")
        print(f"{'=' * 70}")

        clean_url = url.split('?')[0]

        ydl_opts = {
            'quiet': True,  # Keep quiet for production logs
            'no_warnings': True,
            'skip_download': True,
            'format': 'best[ext=mp4]/best',  # Prefer mp4 for mobile
            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

            if not info:
                return None

            video_url = None
            formats = info.get('formats', [])

            # Find best MP4 format
            for fmt in reversed(formats):
                if fmt.get('ext') == 'mp4' and fmt.get('url'):
                    video_url = fmt['url']
                    break

            # Fallback
            if not video_url:
                video_url = info.get('url')

            if not video_url:
                print("✗ No video URL found")
                return None

            print(f"✓ Video info extracted successfully")

            return {
                'video_url': video_url,
                'username': info.get('uploader', 'Unknown'),
                'caption': info.get('description', '')[:200] or info.get('title', ''),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'title': info.get('title', 'Instagram Video'),
                'ext': info.get('ext', 'mp4')
            }

    except yt_dlp.utils.DownloadError as e:
        print(f"✗ yt-dlp Error: {str(e)}")
        return None
    except Exception as e:
        print(f"✗ Unexpected Error: {str(e)}")
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/info', methods=['POST', 'OPTIONS'])
def get_reel_info():
    """Get video info without downloading - used for initial fetch"""
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url or 'instagram.com' not in url:
            return jsonify({'error': 'Please provide a valid Instagram URL'}), 400

        result = get_video_info_ytdlp(url)

        if not result:
            return jsonify({'error': 'Could not fetch video info. Possible private post or rate limit.'}), 400

        # NOTE: The client should now use the 'shortcode' to call the /api/stream-video route.
        shortcode = extract_shortcode(url)

        return jsonify({
            'success': True,
            'message': '✓ Video fetched successfully',
            'video_url': result['video_url'],  # This is a short-lived URL
            'owner_username': result.get('username', 'Unknown'),
            'shortcode': shortcode,
            'thumbnail': result.get('thumbnail', ''),
            'video_duration': result.get('duration', None),
            'title': result.get('title', 'Instagram Video')
        })

    except Exception as e:
        print(f"✗ Info error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/stream-video/<shortcode>', methods=['GET'])
def stream_video_file(shortcode):
    """
    🚀 FIXED: Streams the video file directly from the source URL.
    This prevents server/browser timeouts (pending -> fails) on mobile devices
    by immediately sending data chunks to the client.
    """
    instagram_url = f"https://www.instagram.com/reel/{shortcode}/"
    filename = f"instagram_reel_{shortcode}.mp4"

    try:
        # 1. Get the direct, temporary video URL using yt-dlp
        info = get_video_info_ytdlp(instagram_url)
        if not info or not info.get('video_url'):
            return jsonify({'error': 'Could not find video URL to stream.'}), 404

        direct_video_url = info['video_url']

        # 2. Start a streaming request to the direct video URL
        # We pass the client's Range header to the source for proper streaming/resuming.
        headers = {
            'User-Agent': request.headers.get('User-Agent',
                                              'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15'),
            'Range': request.headers.get('Range', '')  # Crucial for mobile Range requests
        }

        # Set a reasonable timeout for the total stream connection
        r = requests.get(direct_video_url, headers=headers, stream=True, timeout=300)

        # Check for 200 (full content) or 206 (partial content)
        if r.status_code not in (200, 206):
            print(f"✗ Failed to get direct video stream. Status: {r.status_code}")
            return jsonify({'error': f'Failed to stream video from source. Status: {r.status_code}'}), 500

        # 3. Generator to yield chunks of the stream
        def generate_stream():
            try:
                # Use iter_content to read data in chunks
                for chunk in r.iter_content(chunk_size=8192):
                    yield chunk
            except Exception as e:
                # Log streaming error but let the stream close
                print(f"Streaming inner error: {e}")
            finally:
                # Ensure connection is closed
                r.close()

        # 4. Construct the Final Response
        response_headers = {
            # Forces the browser to download
            'Content-Disposition': f'attachment; filename="{filename}"',
            # Pass through critical streaming headers from the video source
            'Accept-Ranges': r.headers.get('Accept-Ranges', 'bytes'),
            'Content-Length': r.headers.get('Content-Length'),
            'Content-Range': r.headers.get('Content-Range'),  # Only present for 206 status
            # Important caching headers for mobile
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        }

        # Use the status code from the source (200 or 206)
        response = Response(
            stream_with_context(generate_stream()),
            status=r.status_code,
            mimetype='video/mp4',
            headers=response_headers
        )

        return response

    except Exception as e:
        print(f"✗ Streaming Error: {str(e)}")
        # This occurs if requests.get() fails (e.g., DNS, initial timeout)
        return jsonify({'error': f'Download/Streaming failed: {str(e)}'}), 500


# --- Removed the OLD, BLOCKING download_video_file route ---
# It was removed because the blocking I/O caused the mobile timeout issue.
# The new route is: /api/stream-video/<shortcode>


# --- HEALTH AND TEST ROUTES (Kept for completeness) ---

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        import yt_dlp
        version = yt_dlp.version.__version__
        return jsonify({
            'status': '✓ healthy',
            'method': 'yt-dlp (FREE)',
            'yt_dlp_version': version,
            'mobile_optimized': True,
            'supports_range_requests': True
        })
    except Exception as e:
        return jsonify({
            'status': '✗ error',
            'error': str(e)
        }), 500


@app.route('/test', methods=['GET'])
def test_download():
    """Test with a sample URL"""
    try:
        test_url = "https://www.instagram.com/reel/DPB75Z9DGjb/"  # Sample reel

        print(f"\n{'=' * 70}")
        print(f"🧪 TESTING")
        print(f"{'=' * 70}")

        result = get_video_info_ytdlp(test_url)

        if result:
            return jsonify({
                'status': '✓ SUCCESS',
                'message': 'yt-dlp is working and retrieved a direct URL for streaming.',
                'test_url': test_url,
                'video_found': True,
                'video_info': {
                    'title': result.get('title', ''),
                    'duration': result.get('duration', 0),
                    'has_video_url': bool(result.get('video_url'))
                },
                'mobile_compatible': True
            })
        else:
            return jsonify({
                'status': '✗ FAILED',
                'message': 'Could not fetch video info for test URL (it might be private or deleted).',
            }), 400

    except Exception as e:
        return jsonify({
            'status': '✗ ERROR',
            'error': str(e),
        }), 500


if __name__ == '__main__':
    print(f"\n{'=' * 70}")
    print(f"🚀 Flask Instagram Downloader - FIXED & STREAMING")
    print(f"{'=' * 70}")
    print(f"✓ Fixed mobile 'pending' issue by switching to **direct streaming**.")
    print(f"✓ New stream endpoint: /api/stream-video/<shortcode>")
    print(f"✓ Health check: http://localhost:5000/health\n")

    app.run(debug=True, host='0.0.0.0', port=5000)