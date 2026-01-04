document.addEventListener("DOMContentLoaded", function () {
  const form = document.querySelector("form");
  const button = form.querySelector("button");
  const loading = document.querySelector(".loading");

  form.addEventListener("submit", function () {
    button.disabled = true;
    button.innerText = "جارٍ المعالجة...";
    loading.style.display = "block";
  });
});
