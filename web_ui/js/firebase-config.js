// IMPORTANT: Replace with your actual Firebase project configuration!
// You can find this in the Firebase console:
// Project settings > General > Your apps > Web app > Firebase SDK snippet > Config
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
  appId: "YOUR_APP_ID",
  measurementId: "YOUR_MEASUREMENT_ID" // Optional, for Google Analytics
};

// Initialize Firebase
try {
  if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
  }
  const db = firebase.firestore(); // Using Firestore
  const auth = firebase.auth();     // Using Firebase Auth (though not heavily in this part)

  // You can also export them if needed in other modules, though for a single app.js, global firebase object is often used.
  // window.db = db;
  // window.auth = auth;

  console.log("Firebase SDK initialized successfully.");
} catch (e) {
  console.error("Error initializing Firebase:", e);
  // Display error to user or disable Firebase-dependent features
  document.body.innerHTML = '<h1>Error initializing Firebase. Please check your firebase-config.js and console.</h1>';
}
