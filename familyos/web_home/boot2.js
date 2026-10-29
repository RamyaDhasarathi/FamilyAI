(function () {
  var stage = document.getElementById('stage2'), lineup = document.getElementById('lineup');
  if (!stage || !lineup) return;
  function fit() {
    var w = stage.clientWidth, small = w < 700;
    /* a phone-width screen shows the tablet and the phone, larger, and leaves the display and watch off the edge */
    var from = small ? 224 : 0, span = small ? 760 : 1000, k = Math.min(1, w / span);
    lineup.style.transform = 'scale(' + k + ')';
    lineup.style.transformOrigin = 'top left';
    lineup.style.marginLeft = '0';
    lineup.style.left = small ? (-from * k + (w - span * k) / 2) + 'px' : ((w - 1000 * k) / 2) + 'px';
    stage.style.height = (560 * k) + 'px';
  }
  fit(); window.addEventListener('resize', fit);
})();
