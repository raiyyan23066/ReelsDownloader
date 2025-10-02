from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file
import yt_dlp
import re
import os
import tempfile
import json
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='../templates', static_folder='../static')

from flask_cors import CORS

# Enable CORS for mobile browsers
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Range"],
        "expose_headers": ["Content-Range", "Accept-Ranges", "Content-Length"]
    }
})


def extract_shortcode(url):
    """Extract shortcode from Instagram URL with query parameters"""
    # Remove query parameters like ?igsh=...
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
    Get video info using yt-dlp
    Optimized for mobile compatibility
    """
    try:
        print(f"\n{'=' * 70}")
        print(f"Fetching: {url}")
        print(f"{'=' * 70}")

        # Clean URL - remove query parameters
        clean_url = url.split('?')[0]

        # Mobile-friendly yt-dlp options
        ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'skip_download': True,
            'format': 'best[ext=mp4]/best',  # Prefer mp4 for mobile
            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Extracting video info...")
            info = ydl.extract_info(clean_url, download=False)

            if not info:
                print("✗ No info returned")
                return None

            # Find best video format for mobile
            video_url = None
            formats = info.get('formats', [])

            # Prefer mp4 format for mobile compatibility
            for fmt in reversed(formats):
                if fmt.get('ext') == 'mp4' and fmt.get('url'):
                    video_url = fmt['url']
                    break

            # Fallback to any video URL
            if not video_url:
                video_url = info.get('url')

            if not video_url:
                print("✗ No video URL found")
                return None

            print(f"✓ Video info extracted successfully")
            print(f"  - Title: {info.get('title', 'Unknown')[:50]}")
            print(f"  - Uploader: {info.get('uploader', 'Unknown')}")
            print(f"  - Duration: {info.get('duration', 0)}s")
            print(f"  - Format: {info.get('ext', 'unknown')}")

            return {
                'video_url': video_url,
                'username': info.get('uploader', 'Unknown'),
                'caption': info.get('description', '')[:200] or info.get('title', ''),
                'likes': info.get('like_count', 0),
                'views': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'title': info.get('title', 'Instagram Video'),
                'ext': info.get('ext', 'mp4')
            }

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        print(f"✗ yt-dlp Error: {error_msg}")

        if "Private" in error_msg or "login" in error_msg.lower():
            print("  → Video is private or requires login")
        elif "429" in error_msg:
            print("  → Rate limited by Instagram")
        elif "404" in error_msg:
            print("  → Video not found or deleted")

        return None
    except Exception as e:
        print(f"✗ Unexpected Error: {str(e)}")
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/download', methods=['POST', 'OPTIONS'])
def download_reel():
    """API endpoint to get video info"""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response, 200

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        if 'instagram.com' not in url:
            return jsonify({'error': 'Please provide a valid Instagram URL'}), 400

        shortcode = extract_shortcode(url)
        if not shortcode:
            return jsonify({'error': 'Invalid Instagram URL format'}), 400

        print(f"\n🔄 Processing shortcode: {shortcode}")

        # Get video info using yt-dlp
        result = get_video_info_ytdlp(url)

        if not result or not result.get('video_url'):
            return jsonify({
                'error': 'Could not fetch video. Possible reasons:\n\n' +
                         '• Post is private\n' +
                         '• Video was deleted\n' +
                         '• Instagram rate limiting\n' +
                         '• Invalid URL\n\n' +
                         f'Shortcode: {shortcode}\n\n' +
                         '💡 Try updating yt-dlp: pip install --upgrade yt-dlp'
            }), 400

        print(f"✓ Success! Video ready for download")

        return jsonify({
            'success': True,
            'message': '✓ Video fetched successfully',
            'video_url': result['video_url'],
            'caption': result.get('caption', ''),
            'likes': result.get('likes', 0),
            'views': result.get('views', 0),
            'owner': result.get('username', 'Unknown'),
            'shortcode': shortcode,
            'thumbnail': result.get('thumbnail', ''),
            'duration': result.get('duration', 0),
            'title': result.get('title', 'Instagram Video'),
            'date': ''
        })

    except Exception as e:
        print(f"✗ Server error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/download-video/<shortcode>', methods=['GET'])
def download_video_file(shortcode):
    """
    Download video file - Optimized for mobile browsers
    Supports Range requests for video streaming on mobile
    """
    try:
        # Build Instagram URL
        instagram_url = f"https://www.instagram.com/reel/{shortcode}/"

        print(f"\n📥 Download request for: {shortcode}")
        print(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")

        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, f'{shortcode}.mp4')

        print(f"Downloading to: {output_path}")

        # yt-dlp download options
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'best[ext=mp4]/best',
            'quiet': False,
            'no_warnings': False,
            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([instagram_url])

        if not os.path.exists(output_path):
            print("✗ Download failed - file not found")
            return jsonify({'error': 'Download failed'}), 400

        file_size = os.path.getsize(output_path)
        print(f"✓ Downloaded successfully ({file_size / 1024 / 1024:.2f} MB)")

        filename = f"instagram_reel_{shortcode}.mp4"

        # Handle Range requests for mobile video streaming
        range_header = request.headers.get('Range', None)

        if range_header:
            # Mobile browser requesting specific byte range
            print(f"📱 Mobile range request: {range_header}")

            byte_start = 0
            byte_end = file_size - 1

            # Parse range header (e.g., "bytes=0-1023")
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                byte_start = int(match.group(1))
                if match.group(2):
                    byte_end = int(match.group(2))

            length = byte_end - byte_start + 1

            def generate():
                try:
                    with open(output_path, 'rb') as f:
                        f.seek(byte_start)
                        remaining = length
                        while remaining > 0:
                            chunk_size = min(8192, remaining)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            yield chunk
                finally:
                    # Cleanup temp files
                    try:
                        os.remove(output_path)
                        os.rmdir(temp_dir)
                    except:
                        pass

            response = Response(
                generate(),
                206,  # Partial Content status for mobile
                mimetype='video/mp4',
                headers={
                    'Content-Range': f'bytes {byte_start}-{byte_end}/{file_size}',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(length),
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Cache-Control': 'no-cache',
                }
            )

        else:
            # Standard download (non-range request)
            print("💻 Standard download request")

            def generate():
                try:
                    with open(output_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    # Cleanup
                    try:
                        os.remove(output_path)
                        os.rmdir(temp_dir)
                    except:
                        pass

            response = Response(
                generate(),
                mimetype='video/mp4',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Content-Length': str(file_size),
                    'Accept-Ranges': 'bytes',
                    'Cache-Control': 'no-cache',
                }
            )

        return response

    except Exception as e:
        print(f"✗ Download error: {str(e)}")
        # Cleanup on error
        try:
            if 'output_path' in locals() and os.path.exists(output_path):
                os.remove(output_path)
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except:
            pass

        return jsonify({'error': f'Download failed: {str(e)}'}), 500


@app.route('/api/info', methods=['POST', 'OPTIONS'])
def get_reel_info():
    """Get video info without downloading"""
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        result = get_video_info_ytdlp(url)

        if not result:
            return jsonify({'error': 'Could not fetch video info'}), 400

        return jsonify({
            'success': True,
            'is_video': True,
            'caption': result.get('caption', ''),
            'likes': result.get('likes', 0),
            'views': result.get('views', 0),
            'comments': 0,
            'date': '',
            'owner_username': result.get('username', 'Unknown'),
            'video_url': result['video_url'],
            'thumbnail': result.get('thumbnail', ''),
            'video_duration': result.get('duration', None),
            'title': result.get('title', '')
        })

    except Exception as e:
        print(f"✗ Info error: {str(e)}")
        return jsonify({'error': f'Error: {str(e)}'}), 500


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
            'requires_api_key': False,
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
    """Test with the exact URL you provided"""
    try:
        # Your exact test URL
        test_url = "https://www.instagram.com/reel/DPB75Z9DGjb/?igsh=cG8zeXR2azlxa3By"

        print(f"\n{'=' * 70}")
        print(f"🧪 TESTING WITH YOUR URL")
        print(f"{'=' * 70}")

        result = get_video_info_ytdlp(test_url)

        if result:
            return jsonify({
                'status': '✓ SUCCESS',
                'message': 'yt-dlp is working perfectly!',
                'test_url': test_url,
                'shortcode': 'DPB75Z9DGjb',
                'video_found': True,
                'video_info': {
                    'title': result.get('title', ''),
                    'username': result.get('username', ''),
                    'duration': result.get('duration', 0),
                    'likes': result.get('likes', 0),
                    'has_video_url': bool(result.get('video_url'))
                },
                'mobile_compatible': True
            })
        else:
            return jsonify({
                'status': '✗ FAILED',
                'message': 'Could not fetch video',
                'test_url': test_url,
                'possible_reasons': [
                    'Video is private',
                    'Instagram blocked request',
                    'yt-dlp needs update'
                ]
            }), 400

    except Exception as e:
        return jsonify({
            'status': '✗ ERROR',
            'error': str(e),
            'test_url': test_url
        }), 500


if __name__ == '__main__':
    print(f"\n{'=' * 70}")
    print(f"🚀 Flask Instagram Downloader - Mobile Optimized")
    print(f"{'=' * 70}")
    print(f"✓ Using yt-dlp (FREE - No API keys required)")
    print(f"✓ Mobile-friendly video streaming (Range requests)")
    print(f"✓ Works on iOS Safari, Android Chrome, Desktop browsers")
    print(f"{'=' * 70}\n")

    # Check yt-dlp
    try:
        import yt_dlp

        print(f"✓ yt-dlp version: {yt_dlp.version.__version__}")
    except ImportError:
        print("✗ yt-dlp not installed!")
        print("  Run: pip install yt-dlp")

    print(f"\n📱 Test endpoint: http://localhost:5000/test")
    print(f"❤️  Health check: http://localhost:5000/health\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
