document.addEventListener("DOMContentLoaded", function () {
    // 找到所有外部链接，并设置 target="_blank"
    var links = document.querySelectorAll("a.external");
    for (var i = 0; i < links.length; i++) {
        links[i].setAttribute("target", "_blank");
    }
});
