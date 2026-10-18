const chat = document.getElementById("chat");
const form = document.getElementById("ask-form");
const input = document.getElementById("question");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function renderMarkdown(el, text) {
  el.innerHTML = marked.parse(text);
  chat.scrollTop = chat.scrollHeight;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  addMessage("user", question);
  input.value = "";
  const pending = addMessage("assistant", "Thinking...");

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    const data = await res.json();
    renderMarkdown(pending, data.answer);
    if (data.sources?.length) {
      const pages = [...new Set(data.sources.map(s => s.page_number))];
      const sourceLine = document.createElement("div");
      sourceLine.className = "sources";
      sourceLine.textContent = "Pages: " + pages.join(", ");
      pending.appendChild(sourceLine);

      const imageUrls = [...new Set(data.sources.flatMap(s => s.image_urls))];
      if (imageUrls.length) {
        const gallery = document.createElement("div");
        gallery.className = "image-gallery";
        for (const url of imageUrls) {
          const img = document.createElement("img");
          img.src = url;
          img.loading = "lazy";
          gallery.appendChild(img);
        }
        pending.appendChild(gallery);
      }
    }
  } catch (err) {
    pending.textContent = "Error: " + err.message;
  }
});
