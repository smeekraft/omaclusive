import QtQuick
import Quickshell
import qs.Ui

// Omaclusive in the Omarchy bar: one calm icon, no animation, no blinking.
// Click: start Omaclusive full screen. If it is not installed yet, open a
// terminal that runs this plugin's own install.sh (no root rights) so the
// user sees every step. `omarchy plugin add` itself never runs anything.
BarWidget {
  id: root
  moduleName: "smeekraft.omaclusive"

  readonly property string home: Quickshell.env("HOME")
  readonly property string pluginDir: {
    var url = Qt.resolvedUrl(".").toString()
    return decodeURIComponent(url.replace(/^file:\/\//, "")).replace(/\/$/, "")
  }
  readonly property string starter: home + "/.local/share/omaclusive/start-talker.sh"

  function quote(text) {
    return "'" + String(text).replace(/'/g, "'\\''") + "'"
  }

  function start() {
    var cmd = "if [ -x " + quote(root.starter) + " ]; then exec uwsm-app -- " + quote(root.starter) + "; "
      + "else exec omarchy-launch-floating-terminal-with-presentation "
      + quote("cd " + quote(root.pluginDir) + " && ./install.sh && uwsm-app -- " + quote(root.starter)) + "; fi"
    Quickshell.execDetached(["bash", "-lc", cmd])
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Material Design "remote-tv" (nerd font md-remote_tv, U+F0EC5)
    text: String.fromCodePoint(0xf0ec5)
    tooltipText: "Omaclusive"
    onPressed: function(mouseButton) { root.start() }
  }
}
