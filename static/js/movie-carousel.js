
document.addEventListener("DOMContentLoaded", () => {
    const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    document.querySelectorAll(".movie-poster").forEach((poster) => {
        const images = Array.from(poster.querySelectorAll("img"));

        // Keep single-poster cards exactly as they are for now.
        if (images.length < 2) {
            return;
        }

        let currentIndex = 0;
        let timer = null;

        poster.classList.add("poster-carousel");

        const controls = document.createElement("div");
        controls.className = "poster-carousel-controls";

        const previousButton = document.createElement("button");
        previousButton.type = "button";
        previousButton.className = "poster-carousel-prev";
        previousButton.textContent = "‹";
        previousButton.setAttribute("aria-label", "Previous poster");

        const nextButton = document.createElement("button");
        nextButton.type = "button";
        nextButton.className = "poster-carousel-next";
        nextButton.textContent = "›";
        nextButton.setAttribute("aria-label", "Next poster");

        const dots = document.createElement("div");
        dots.className = "poster-carousel-dots";
        dots.setAttribute("aria-label", "Choose a poster");

        const dotButtons = images.map((image, index) => {
            image.classList.add("poster-carousel-image");
            image.hidden = index !== 0;

            const dot = document.createElement("button");
            dot.type = "button";
            dot.className = "poster-carousel-dot";
            dot.setAttribute("aria-label", `Show poster ${index + 1}`);
            dot.setAttribute("aria-current", index === 0 ? "true" : "false");

            dot.addEventListener("click", () => {
                showImage(index);
                restartTimer();
            });

            dots.appendChild(dot);
            return dot;
        });

        function showImage(index) {
            currentIndex = (index + images.length) % images.length;

            images.forEach((image, imageIndex) => {
                image.hidden = imageIndex !== currentIndex;
            });

            dotButtons.forEach((dot, dotIndex) => {
                dot.setAttribute(
                    "aria-current",
                    dotIndex === currentIndex ? "true" : "false"
                );
            });
        }

        function stopTimer() {
            if (timer !== null) {
                window.clearInterval(timer);
                timer = null;
            }
        }

        function startTimer() {
            stopTimer();

            if (
                prefersReducedMotion ||
                poster.matches(":hover") ||
                poster.contains(document.activeElement)
            ) {
                return;
            }

            timer = window.setInterval(() => {
                showImage(currentIndex + 1);
            }, 4000);
        }

        function restartTimer() {
            stopTimer();
            startTimer();
        }

        previousButton.addEventListener("click", () => {
            showImage(currentIndex - 1);
            restartTimer();
        });

        nextButton.addEventListener("click", () => {
            showImage(currentIndex + 1);
            restartTimer();
        });

        poster.addEventListener("mouseenter", stopTimer);
        poster.addEventListener("mouseleave", startTimer);

        poster.addEventListener("focusin", stopTimer);
        poster.addEventListener("focusout", (event) => {
            if (!poster.contains(event.relatedTarget)) {
                startTimer();
            }
        });

        controls.append(previousButton, dots, nextButton);
        poster.appendChild(controls);

        startTimer();
    });
});
