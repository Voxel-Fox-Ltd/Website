function scrollToMessage(event, id) {
    var element = document.getElementById('message-' + id);
    if (element) {
        event.preventDefault();
        element.classList.add('chatlog__message--highlighted');
        window.scrollTo({
            top: element.getBoundingClientRect().top - document.body.getBoundingClientRect().top - (window.innerHeight / 2),
            behavior: 'smooth'
        });
        window.setTimeout(function() {
            element.classList.remove('chatlog__message--highlighted');
        }, 2000);
    }
}

function showSpoiler(event, element) {
    if (element && element.classList.contains('spoiler--hidden')) {
        event.preventDefault();
        element.classList.remove('spoiler--hidden');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.pre--multiline').forEach(block => hljs.highlightBlock(block));
    twemoji.parse(document.body);
    for(e of document.getElementsByClassName("chatlog__timestamp")) {
        timestamp = parseInt(e.dataset.timestamp) * 1_000
        e.innerHTML = moment(timestamp).calendar();
    }
    window.status = "RenderingComplete";
});
