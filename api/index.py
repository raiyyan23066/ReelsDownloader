from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import instaloader
import re
import requests

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Initialize Instaloader
L = instaloader.Instaloader(
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False
)


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


@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


@app.route('/api/download', methods=['POST'])
def download_reel():
    """Handle reel download requests"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Extract shortcode
        shortcode = extract_shortcode(url)
        if not shortcode:
            return jsonify({'error': 'Invalid Instagram URL'}), 400

        try:
            # Get post data
            post = instaloader.Post.from_shortcode(L.context, shortcode)

            # Check if it's a video
            if not post.is_video:
                return jsonify({'error': 'This post is not a video'}), 400

            # Get video URL directly
            video_url = post.video_url

            return jsonify({
                'success': True,
                'message': 'Reel information retrieved successfully',
                'video_url': video_url,
                'caption': post.caption[:200] if post.caption else 'No caption',
                'likes': post.likes,
                'owner': post.owner_username,
                'shortcode': shortcode,
                'date': post.date.isoformat()
            })

        except instaloader.exceptions.InstaloaderException as e:
            return jsonify({'error': f'Instagram error: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/download-video/<shortcode>')
def download_video_file(shortcode):
    """Proxy download endpoint - forces video download"""
    try:
        # Get post data
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if not post.is_video:
            return jsonify({'error': 'Not a video'}), 400

        # Get video URL
        video_url = post.video_url

        # Fetch video from Instagram with streaming and optimized settings
        response = requests.get(
            video_url,
            stream=True,
            timeout=30,  # Add timeout
            headers={'User-Agent': 'Mozilla/5.0'}  # Add user agent
        )
        response.raise_for_status()

        # Generate filename
        filename = f"instagram_reel_{shortcode}.mp4"

        # Create a Flask response that streams the video with larger chunks
        def generate():
            for chunk in response.iter_content(chunk_size=65536):  # Increased from 8192 to 65536 (64KB)
                if chunk:
                    yield chunk

        # Return as downloadable file
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
    """Get reel information without downloading"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        shortcode = extract_shortcode(url)
        if not shortcode:
            return jsonify({'error': 'Invalid Instagram URL'}), 400

        post = instaloader.Post.from_shortcode(L.context, shortcode)

        return jsonify({
            'success': True,
            'is_video': post.is_video,
            'caption': post.caption[:200] if post.caption else 'No caption',
            'likes': post.likes,
            'comments': post.comments,
            'date': post.date.isoformat(),
            'owner_username': post.owner_username,
            'video_url': post.video_url if post.is_video else None,
            'video_duration': post.video_duration if post.is_video else None
        })

    except Exception as e:
        return jsonify({'error': f'Error fetching info: {str(e)}'}), 500


# For local development
if __name__ == '__main__':
    app.run(debug=True)
