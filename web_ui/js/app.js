// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Check if Firebase is initialized (from firebase-config.js)
    if (typeof firebase === 'undefined' || !firebase.apps.length) {
        console.error("Firebase SDK not loaded or initialized. Check firebase-config.js and script order.");
        alert("Firebase is not configured. The application cannot start.");
        return;
    }

    const db = firebase.firestore();
    // const auth = firebase.auth(); // If needed for user login to the admin panel itself

    // --- Configuration ---
    // This APP_ID should ideally match the one used by your Cloud Function and ESP32 script.
    // For a real app, you might get this from a config file, environment, or Firestore itself.
    const APP_ID = "default-scrobbler-app"; // IMPORTANT: Replace with your actual App ID

    // This TARGET_USER_ID is the one for whom Last.fm scrobbling will be performed.
    // It should match the TARGET_USER_ID environment variable in your Cloud Function.
    // The Web UI helps set up the Last.fm credentials for this user.
    // For simplicity, hardcoding, but ideally, this would be dynamically set or input by an admin.
    const TARGET_USER_ID = "YOUR_USER_ID_FROM_WEB_UI"; // IMPORTANT: Replace with the actual User ID configured in CF.

    document.getElementById('target-user-id-display').textContent = TARGET_USER_ID || "Not Set";


    // --- DOM Elements ---
    const lastfmApiKeyInput = document.getElementById('lastfm-api-key');
    const lastfmApiSecretInput = document.getElementById('lastfm-api-secret');
    const authLastfmBtn = document.getElementById('auth-lastfm-btn');
    const lastfmAuthStatus = document.getElementById('lastfm-auth-status');

    const rfidTagInput = document.getElementById('rfid-tag');
    const artistNameInput = document.getElementById('artist-name');
    const albumTitleInput = document.getElementById('album-title');
    const saveAlbumBtn = document.getElementById('save-album-btn');
    const clearAlbumFormBtn = document.getElementById('clear-album-form-btn');
    const albumListDiv = document.getElementById('album-list');

    const refreshLogsBtn = document.getElementById('refresh-logs-btn');
    const logListDiv = document.getElementById('log-list');

    let currentEditRfidTag = null; // To track if we are editing an existing album

    // --- Firebase Firestore Paths ---
    const lastfmConfigPath = `artifacts/${APP_ID}/users/${TARGET_USER_ID}/config/lastfm`;
    const lastfmSessionPath = `artifacts/${APP_ID}/users/${TARGET_USER_ID}/config/lastfm_session`;
    const albumsBasePath = `artifacts/${APP_ID}/public/data/albums`;
    const logsBasePath = `artifacts/${APP_ID}/public/data/script_logs`;

    // --- Last.fm Authentication ---
    authLastfmBtn.addEventListener('click', async () => {
        const apiKey = lastfmApiKeyInput.value.trim();
        const apiSecret = lastfmApiSecretInput.value.trim();

        if (!TARGET_USER_ID || TARGET_USER_ID === "YOUR_USER_ID_FROM_WEB_UI") {
            alert("Please set the TARGET_USER_ID in app.js first.");
            return;
        }
        if (!apiKey || !apiSecret) {
            alert("Please enter both Last.fm API Key and API Secret.");
            return;
        }

        lastfmAuthStatus.textContent = "Saving API Key & Secret...";
        try {
            // Save API Key and Secret to Firestore for the TARGET_USER_ID
            // The Cloud Function will use these.
            await db.doc(lastfmConfigPath).set({
                apiKey: apiKey,
                apiSecret: apiSecret,
                updatedAt: firebase.firestore.FieldValue.serverTimestamp()
            }, { merge: true });
            lastfmAuthStatus.textContent = "API Key & Secret saved. Now, let's get a session key.";

            // TODO: Implement actual Last.fm Web Auth Flow (OAuth-like)
            // 1. Construct the auth URL: http://www.last.fm/api/auth/?api_key=YOUR_API_KEY&cb=YOUR_CALLBACK_URL
            //    YOUR_CALLBACK_URL would be this app, perhaps with specific query params.
            // 2. Redirect the user to this URL.
            // 3. After user authorizes on Last.fm, they are redirected back to YOUR_CALLBACK_URL with a `token`.
            // 4. On callback, this app should take that `token`, make a signed API call to `auth.getSession`
            //    using the API key, API secret, and the token.
            // 5. This call returns a session key (`sk`) and username.
            // 6. Save this `sk` and `username` to `lastfmSessionPath` in Firestore.

            alert("Placeholder: Last.fm API Key & Secret saved. " +
                  "The next step would be to redirect to Last.fm for authorization. " +
                  "After authorization and redirect back, the session key would be fetched and saved. " +
                  "This part needs to be fully implemented.");

            // Example of what you'd save after getting session key:
            // const sessionKey = " полученный_ключ_сессии ";
            // const lastfmUsername = " полученное_имя_пользователя ";
            // await db.doc(lastfmSessionPath).set({
            //     sessionKey: sessionKey,
            //     name: lastfmUsername, // Last.fm usually returns 'name' for username
            //     updatedAt: firebase.firestore.FieldValue.serverTimestamp()
            // }, { merge: true });
            // lastfmAuthStatus.textContent = `Session key for ${lastfmUsername} saved!`;

            loadLastfmConfig(); // Reload to show current status
        } catch (error) {
            console.error("Error during Last.fm auth setup:", error);
            lastfmAuthStatus.textContent = `Error: ${error.message}`;
            alert(`Error saving Last.fm credentials: ${error.message}`);
        }
    });

    async function loadLastfmConfig() {
        try {
            const configDoc = await db.doc(lastfmConfigPath).get();
            const sessionDoc = await db.doc(lastfmSessionPath).get();

            if (configDoc.exists) {
                const configData = configDoc.data();
                lastfmApiKeyInput.value = configData.apiKey || "";
                lastfmApiSecretInput.value = configData.apiSecret || "";
            }
            if (sessionDoc.exists) {
                const sessionData = sessionDoc.data();
                if (sessionData.sessionKey && sessionData.name) {
                    lastfmAuthStatus.textContent = `Authenticated with Last.fm as '${sessionData.name}'. Session key is stored.`;
                } else {
                    lastfmAuthStatus.textContent = "API Key/Secret found, but session key is missing or incomplete. Please complete authentication.";
                }
            } else {
                 if(configDoc.exists) {
                    lastfmAuthStatus.textContent = "API Key/Secret found, but session key is missing. Please complete authentication.";
                 } else {
                    lastfmAuthStatus.textContent = "Not configured. Please enter API Key/Secret and authenticate.";
                 }
            }
        } catch (error) {
            console.error("Error loading Last.fm config:", error);
            lastfmAuthStatus.textContent = "Error loading configuration.";
        }
    }


    // --- Album Management ---
    saveAlbumBtn.addEventListener('click', async () => {
        const tagId = rfidTagInput.value.trim();
        const artist = artistNameInput.value.trim();
        const album = albumTitleInput.value.trim();

        if (!tagId || !artist || !album) {
            alert("Please fill in all album fields: RFID Tag, Artist, and Album.");
            return;
        }

        const albumData = {
            artist: artist,
            album: album,
            rfid_tag: tagId, // Store tag_id also in document for easier querying if needed
            updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        };

        try {
            // Document ID in Firestore will be the RFID tag itself
            await db.collection(albumsBasePath).doc(tagId).set(albumData, { merge: true });
            alert(`Album '${album}' by '${artist}' for RFID tag '${tagId}' saved successfully!`);
            clearAlbumForm();
            loadAlbums(); // Refresh the list
        } catch (error) {
            console.error("Error saving album:", error);
            alert(`Error saving album: ${error.message}`);
        }
    });

    clearAlbumFormBtn.addEventListener('click', clearAlbumForm);

    function clearAlbumForm() {
        rfidTagInput.value = "";
        artistNameInput.value = "";
        albumTitleInput.value = "";
        rfidTagInput.disabled = false; // Enable RFID tag input for new entries
        currentEditRfidTag = null;
        saveAlbumBtn.textContent = "Save Album";
    }

    async function loadAlbums() {
        albumListDiv.innerHTML = "<p>Loading albums...</p>";
        try {
            const snapshot = await db.collection(albumsBasePath).orderBy("updatedAt", "desc").get();
            if (snapshot.empty) {
                albumListDiv.innerHTML = "<p>No albums found. Add some!</p>";
                return;
            }
            albumListDiv.innerHTML = ""; // Clear loading message
            snapshot.forEach(doc => {
                const album = doc.data();
                const albumId = doc.id; // This is the RFID tag

                const itemDiv = document.createElement('div');
                itemDiv.classList.add('album-item');
                itemDiv.innerHTML = `
                    <div class="album-details">
                        <strong>Tag:</strong> ${albumId}<br>
                        <strong>Artist:</strong> ${album.artist}<br>
                        <strong>Album:</strong> ${album.album}
                    </div>
                    <div class="actions">
                        <button data-id="${albumId}" class="edit-album-btn">Edit</button>,
                        <button data-id="${albumId}" class="delete-album-btn">Delete</button>
                    </div>
                `;
                albumListDiv.appendChild(itemDiv);
            });

            // Add event listeners for edit/delete buttons
            document.querySelectorAll('.edit-album-btn').forEach(button => {
                button.addEventListener('click', (e) => handleEditAlbum(e.target.dataset.id));
            });
            document.querySelectorAll('.delete-album-btn').forEach(button => {
                button.addEventListener('click', (e) => handleDeleteAlbum(e.target.dataset.id));
            });

        } catch (error) {
            console.error("Error loading albums:", error);
            albumListDiv.innerHTML = `<p>Error loading albums: ${error.message}</p>`;
        }
    }

    async function handleEditAlbum(tagId) {
        try {
            const doc = await db.collection(albumsBasePath).doc(tagId).get();
            if (doc.exists) {
                const album = doc.data();
                rfidTagInput.value = tagId;
                artistNameInput.value = album.artist;
                albumTitleInput.value = album.album;
                rfidTagInput.disabled = true; // Disable RFID tag editing, it's the ID
                currentEditRfidTag = tagId;
                saveAlbumBtn.textContent = "Update Album";
                window.scrollTo(0, 0); // Scroll to top to see the form
            }
        } catch (error) {
            console.error("Error fetching album for edit:", error);
        }
    }

    async function handleDeleteAlbum(tagId) {
        if (confirm(`Are you sure you want to delete album for RFID tag '${tagId}'?`)) {
            try {
                await db.collection(albumsBasePath).doc(tagId).delete();
                alert(`Album for RFID tag '${tagId}' deleted successfully.`);
                loadAlbums(); // Refresh list
            } catch (error) {
                console.error("Error deleting album:", error);
                alert(`Error deleting album: ${error.message}`);
            }
        }
    }

    // --- Log Viewing ---
    refreshLogsBtn.addEventListener('click', loadLogs);

    async function loadLogs() {
        logListDiv.innerHTML = "<p>Loading logs...</p>";
        try {
            // Query logs, order by timestamp descending, limit for performance
            const snapshot = await db.collection(logsBasePath)
                                     .orderBy("timestamp", "desc")
                                     .limit(100) // Get latest 100 logs
                                     .get();

            if (snapshot.empty) {
                logListDiv.innerHTML = "<p>No logs found.</p>";
                return;
            }
            logListDiv.innerHTML = ""; // Clear loading message

            // Optional: Use a table for better log formatting
            const table = document.createElement('table');
            table.innerHTML = `<thead><tr>
                <th>Timestamp</th>
                <th>Type</th>
                <th>Source</th>
                <th>Message</th>
                <th>Tag</th>
                <th>Details</th>
            </tr></thead>`;
            const tbody = document.createElement('tbody');
            table.appendChild(tbody);

            snapshot.forEach(doc => {
                const log = doc.data();
                const tr = tbody.insertRow();

                const timestamp = log.timestamp ? new Date(log.timestamp.seconds * 1000).toLocaleString() : 'N/A';
                const type = log.type || 'N/A';
                const source = log.source || 'N/A';
                const message = log.message || '';
                const rfidTag = log.rfid_tag || '';
                const details = log.details ? JSON.stringify(log.details, null, 2) : '';

                tr.insertCell().textContent = timestamp;
                tr.insertCell().textContent = type;
                tr.insertCell().textContent = source;
                tr.insertCell().textContent = message;
                tr.insertCell().textContent = rfidTag;
                tr.insertCell().innerHTML = `<pre>${details}</pre>`; // Use pre for formatted JSON
            });
            logListDiv.appendChild(table);

        } catch (error) {
            console.error("Error loading logs:", error);
            logListDiv.innerHTML = `<p>Error loading logs: ${error.message}</p>`;
        }
    }

    // --- Initial Load ---
    if (TARGET_USER_ID && TARGET_USER_ID !== "YOUR_USER_ID_FROM_WEB_UI") {
        loadLastfmConfig();
    } else {
        lastfmAuthStatus.textContent = "TARGET_USER_ID not set in app.js. Last.fm setup cannot proceed.";
    }
    loadAlbums();
    loadLogs();
});
