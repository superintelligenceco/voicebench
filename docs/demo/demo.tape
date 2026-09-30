# Records docs/assets/demo.gif from the real voicebench CLI.
# Regenerate with: make demo (needs Docker)
Output docs/assets/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1100
Set Height 800
Set Padding 16
Set TypingSpeed 40ms
Set Theme "Dracula"

Hide
Type "cd $(mktemp -d) && clear"
Enter
Show

Type "voicebench example mock-conversation -O demo.yaml"
Sleep 300ms
Enter
Sleep 1s
Type "voicebench run demo.yaml"
Sleep 300ms
Enter
Sleep 6s
Type "ls voicebench-results/*"
Enter
Sleep 3s
