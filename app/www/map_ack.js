// Map tab frame acknowledgement (see app/map_ui.py, Playback).
// The server sends "map_frame_seq" right after each frame's layer patch; custom
// messages are handled in order, so answering it means the frame has reached
// this browser. window.__mapAcks keeps arrival times for the acceptance test.
(function () {
  window.__mapAcks = [];
  // Test hook: the acceptance test sets this (ms) to stand in for a slow link,
  // because Chromium's network throttling does not slow WebSocket messages.
  window.__mapAckDelay = 0;
  function register() {
    Shiny.addCustomMessageHandler("map_frame_seq", function (msg) {
      window.__mapAcks.push({ run: msg.run, seq: msg.seq, t: performance.now() });
      if (window.__mapAcks.length > 5000) window.__mapAcks.shift();
      setTimeout(function () {
        Shiny.setInputValue("map_frame_ack", msg, { priority: "event" });
      }, window.__mapAckDelay || 0);
    });
  }
  if (window.Shiny && Shiny.addCustomMessageHandler) register();
  // Shiny fires shiny:connected through jQuery, so a native listener never sees it.
  else $(document).one("shiny:connected", register);
})();
