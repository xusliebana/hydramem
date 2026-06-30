/* HydraMem docs — scroll reveal + animated counters.
   Works with Material's instant navigation (document$) and full reloads. */

function hmInit() {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- Scroll reveal -------------------------------------------------------
  var revealEls = document.querySelectorAll(".reveal");
  if (reduce || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    revealEls.forEach(function (el) { io.observe(el); });
  }

  // --- Animated counters ---------------------------------------------------
  document.querySelectorAll("[data-count]").forEach(function (el) {
    if (el.dataset.hmDone) return;
    var target = parseFloat(el.getAttribute("data-count")) || 0;
    var suffix = el.getAttribute("data-suffix") || "";
    var dec = parseInt(el.getAttribute("data-dec") || "0", 10);

    if (reduce || !("IntersectionObserver" in window)) {
      el.textContent = target.toFixed(dec) + suffix;
      el.dataset.hmDone = "1";
      return;
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        obs.unobserve(el);
        el.dataset.hmDone = "1";
        var start = null, dur = 1400;
        function step(ts) {
          if (start === null) start = ts;
          var p = Math.min((ts - start) / dur, 1);
          var eased = 0.5 - Math.cos(Math.PI * p) / 2; // easeInOutSine
          el.textContent = (target * eased).toFixed(dec) + suffix;
          if (p < 1) requestAnimationFrame(step);
          else el.textContent = target.toFixed(dec) + suffix;
        }
        requestAnimationFrame(step);
      });
    }, { threshold: 0.5 });
    obs.observe(el);
  });
}

if (typeof document$ !== "undefined" && document$.subscribe) {
  // Material instant navigation
  document$.subscribe(function () { hmInit(); });
} else {
  document.addEventListener("DOMContentLoaded", hmInit);
}
