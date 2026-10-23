// Keep the HTML loading screen visible until the application can render.
const shell = document.getElementById("startup");
const message = document.getElementById("startup-message");
const details = document.getElementById("startup-details");
const timer = setTimeout(() => {
  if (!shell?.isConnected) return;
  message.textContent = "The exchange is taking longer to load.";
  details.textContent =
    "Check the frontend terminal for errors, then reload. For a fresh download, run npm ci in the frontend folder first.";
}, 15000);
import("./main.jsx").catch((error) => {
  clearTimeout(timer);
  if (!shell?.isConnected) return;
  message.textContent = "The exchange could not start.";
  details.textContent =
    error.message + " Check the frontend terminal, then reload this page.";
});
new MutationObserver((_, observer) => {
  if (!shell?.isConnected) {
    clearTimeout(timer);
    observer.disconnect();
  }
}).observe(document.getElementById("root"), { childList: true });
