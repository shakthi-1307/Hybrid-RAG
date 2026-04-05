/* ============================================================
   CONFIGURATION
   ============================================================ */
const API_URL = "http://localhost:8000";

/* ============================================================
   DOM ELEMENTS
   ============================================================ */
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const uploadStatus = document.getElementById('uploadStatus');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const chatHistory = document.getElementById('chatHistory');
const docCount = document.getElementById('docCount');
const refreshStats = document.getElementById('refreshStats');
const sourcesPanel = document.getElementById('sourcesPanel');
const sourcesList = document.getElementById('sourcesList');
const closeSources = document.getElementById('closeSources');

/* ============================================================
   UTILITY FUNCTIONS
   ============================================================ */

// Add message to chat
function addMessage(text, sender, isLoading = false) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', sender);
    
    if (isLoading) {
        messageDiv.id = `loading-${Date.now()}`;
        messageDiv.innerHTML = `
            <div class="loading">
                <span></span><span></span><span></span>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `<div class="message-content">${text}</div>`;
    }
    
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return messageDiv.id;
}

// Update message (for loading → final)
function updateMessage(id, newText) {
    const messageDiv = document.getElementById(id);
    if (messageDiv) {
        messageDiv.innerHTML = `<div class="message-content">${newText}</div>`;
    }
}

// Show status message
function showStatus(message, type = 'success') {
    uploadStatus.textContent = message;
    uploadStatus.className = `status-message ${type}`;
    setTimeout(() => {
        uploadStatus.textContent = '';
        uploadStatus.className = 'status-message';
    }, 5000);
}

// Show sources panel
function showSources(sources) {
    sourcesList.innerHTML = '';
    
    sources.forEach((source, index) => {
        const sourceDiv = document.createElement('div');
        sourceDiv.classList.add('source-item');
        sourceDiv.innerHTML = `
            <strong>📄 Source ${index + 1}</strong>
            ${source.text}
        `;
        sourcesList.appendChild(sourceDiv);
    });
    
    sourcesPanel.classList.remove('hidden');
}

// Fetch database stats
async function fetchStats() {
    try {
        const response = await fetch(`${API_URL}/stats`);
        const data = await response.json();
        docCount.textContent = data.documents || 0;
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

/* ============================================================
   UPLOAD FUNCTIONALITY
   ============================================================ */

uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    
    if (!file) {
        showStatus('⚠️ Please select a PDF file', 'error');
        return;
    }
    
    // Disable button during upload
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';
    showStatus('📤 Uploading and processing...', 'success');
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            showStatus(`✅ ${result.message}`, 'success');
            fetchStats(); // Update document count
        } else {
            showStatus(`❌ ${result.message}`, 'error');
        }
        
    } catch (error) {
        showStatus(`❌ Error: ${error.message}`, 'error');
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload PDF';
    }
});

/* ============================================================
   CHAT FUNCTIONALITY
   ============================================================ */

async function sendMessage() {
    const text = userInput.value.trim();
    
    if (!text) return;
    
    // Add user message
    addMessage(text, 'user');
    userInput.value = '';
    
    // Disable input during processing
    userInput.disabled = true;
    sendBtn.disabled = true;
    
    // Add loading indicator
    const loadingId = addMessage('', 'bot', true);
    
    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: text })
        });
        
        const result = await response.json();
        
        // Update bot message
        if (result.success) {
            updateMessage(loadingId, result.answer);
            
            // Show sources if available
            if (result.sources && result.sources.length > 0) {
                showSources(result.sources);
            }
        } else {
            updateMessage(loadingId, result.answer);
        }
        
    } catch (error) {
        updateMessage(loadingId, `❌ Error: Could not connect to server. Make sure backend is running.`);
        console.error('Chat error:', error);
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}

// Send button click
sendBtn.addEventListener('click', sendMessage);

// Enter key to send
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

/* ============================================================
   SOURCES PANEL
   ============================================================ */

closeSources.addEventListener('click', () => {
    sourcesPanel.classList.add('hidden');
});

refreshStats.addEventListener('click', fetchStats);

/* ============================================================
   INITIALIZATION
   ============================================================ */

// Load stats on page load
fetchStats();

// Focus on input
userInput.focus();

console.log('✅ RAG Frontend Loaded');
console.log(`📡 API URL: ${API_URL}`);