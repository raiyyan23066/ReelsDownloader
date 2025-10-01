async function fetchReelInfo() {
    const url = document.getElementById('reelUrl').value.trim();

    if (!url) {
        showError('Please enter a valid Instagram URL');
        return;
    }

    showLoading();
    hideResult();
    hideError();

    try {
        const response = await axios.post('/api/info', { url });

        if (response.data.success) {
            displayReelInfo(response.data);
        }
    } catch (error) {
        showError(error.response?.data?.error || 'Failed to fetch reel information');
    } finally {
        hideLoading();
    }
}

async function downloadReel() {
    const url = document.getElementById('reelUrl').value.trim();

    if (!url) {
        showError('Please enter a valid Instagram URL');
        return;
    }

    showLoading();
    hideResult();
    hideError();

    try {
        const response = await axios.post('/api/download', { url });

        if (response.data.success) {
            displayDownloadResult(response.data);
        }
    } catch (error) {
        showError(error.response?.data?.error || 'Failed to download reel');
    } finally {
        hideLoading();
    }
}

// NEW: Detect if user is on mobile
function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// NEW: Download function for mobile using server proxy
async function initiateDownload(shortcode) {
    const downloadBtn = event.target;
    const originalText = downloadBtn.innerHTML;

    // Show downloading indicator
    downloadBtn.innerHTML = '⏳ Preparing...';
    downloadBtn.classList.add('opacity-75', 'cursor-wait');
    downloadBtn.style.pointerEvents = 'none';

    if (isMobile()) {
        // For mobile: Use server proxy download
        const downloadUrl = `/api/download-video/${shortcode}`;
        window.location.href = downloadUrl;

        setTimeout(() => {
            downloadBtn.innerHTML = '✅ Check Downloads!';
            setTimeout(() => {
                downloadBtn.innerHTML = originalText;
                downloadBtn.classList.remove('opacity-75', 'cursor-wait');
                downloadBtn.style.pointerEvents = 'auto';
            }, 3000);
        }, 1000);
    } else {
        // For desktop: Use anchor tag
        const downloadUrl = `/api/download-video/${shortcode}`;
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = `instagram_reel_${shortcode}.mp4`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        setTimeout(() => {
            downloadBtn.innerHTML = '✅ Download Started!';
            setTimeout(() => {
                downloadBtn.innerHTML = originalText;
                downloadBtn.classList.remove('opacity-75', 'cursor-wait');
                downloadBtn.style.pointerEvents = 'auto';
            }, 2000);
        }, 1000);
    }
}

function displayReelInfo(data) {
    const resultContent = document.getElementById('resultContent');

    resultContent.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><strong>Owner:</strong> @${data.owner_username}</div>
            <div><strong>Likes:</strong> ${data.likes.toLocaleString()}</div>
            <div><strong>Comments:</strong> ${data.comments.toLocaleString()}</div>
            <div><strong>Date:</strong> ${new Date(data.date).toLocaleDateString()}</div>
            ${data.video_duration ? `<div><strong>Duration:</strong> ${data.video_duration}s</div>` : ''}
        </div>
        ${data.caption ? `<div class="mt-3"><strong>Caption:</strong><br>${escapeHtml(data.caption)}...</div>` : ''}
        ${data.video_url ? `
            <div class="mt-4">
                <a href="${data.video_url}" target="_blank" class="inline-block bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition">
                    ▶️ Open Video
                </a>
            </div>
        ` : ''}
    `;

    showResult();
}

function displayDownloadResult(data) {
    const resultContent = document.getElementById('resultContent');
    const mobileInstructions = isMobile() ?
        '<p class="mt-3 text-sm text-gray-600 text-center">📱 Mobile: Video will open in new tab. Long-press to save!</p>' :
        '<p class="mt-3 text-sm text-gray-600 text-center">💡 Download may take a few seconds</p>';

    resultContent.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><strong>Owner:</strong> @${data.owner}</div>
            <div><strong>Likes:</strong> ${data.likes.toLocaleString()}</div>
        </div>
        ${data.caption ? `<div class="mt-3"><strong>Caption:</strong><br>${escapeHtml(data.caption)}...</div>` : ''}
        <div class="mt-4 flex flex-col sm:flex-row gap-3">
            <button onclick="initiateDownload('${data.shortcode}')"
               class="inline-block flex-1 bg-gradient-to-r from-green-500 to-green-600 text-white px-6 py-3 rounded-lg hover:from-green-600 hover:to-green-700 transition font-semibold text-center cursor-pointer">
                💾 Download Video
            </button>
            <a href="${data.video_url}"
               target="_blank"
               class="inline-block flex-1 bg-gradient-to-r from-blue-500 to-blue-600 text-white px-6 py-3 rounded-lg hover:from-blue-600 hover:to-blue-700 transition font-semibold text-center">
                ▶️ Play Video
            </a>
        </div>
        ${mobileInstructions}
    `;

    showResult();
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function showResult() {
    document.getElementById('result').classList.remove('hidden');
}

function hideResult() {
    document.getElementById('result').classList.add('hidden');
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    document.getElementById('error').classList.remove('hidden');
}

function hideError() {
    document.getElementById('error').classList.add('hidden');
}
