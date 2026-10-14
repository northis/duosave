/* Duosave service worker: the system share sheet navigates to POST /share, and this worker
   turns that navigation into ordinary API requests. There is no caching here at all: only
   POST /share is intercepted, everything else goes to the network without respondWith. */
"use strict";

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "POST" || url.pathname !== "/share") return;
  event.respondWith(handleShare(event.request));
});

/* Read the shared images out of the multipart body and upload them one by one. */
async function handleShare(request) {
  let files;
  try {
    files = (await request.formData()).getAll("images").filter((item) => item instanceof File);
  } catch (err) {
    return Response.redirect("/share?error=empty", 303);
  }
  if (!files.length) return Response.redirect("/share?error=empty", 303);

  const counts = { new: 0, review: 0, skip: 0, dup: 0 };
  let card = 0;
  let error = "";
  for (const file of files) {
    let data = null;
    let ok = false;
    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        headers: { "X-Duosave-Request": "1", "Content-Type": file.type },
        body: file,
      });
      ok = response.ok;
      data = await response.json().catch(() => null);
    } catch (err) {
      error = error || "busy"; /* the upload never reached the server: retry */
      continue;
    }
    if (!ok || !data || typeof data !== "object") {
      error = error || (data && data.error) || "busy";
      continue;
    }
    if (data.outcome === "duplicate") counts.dup += 1;
    else if (data.outcome === "stored" && data.status === "auto") counts.new += 1;
    else if (data.status === "review") counts.review += 1;
    else if (data.status === "skipped") counts.skip += 1;
    if (!card && data.card_id) card = data.card_id;
  }

  const params = [
    `new=${counts.new}`,
    `review=${counts.review}`,
    `skip=${counts.skip}`,
    `dup=${counts.dup}`,
  ];
  if (card) params.push(`card=${card}`);
  if (error) params.push(`error=${error}`);
  return Response.redirect("/share?" + params.join("&"), 303);
}
