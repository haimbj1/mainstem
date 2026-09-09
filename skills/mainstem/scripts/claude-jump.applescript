-- ms://session?name=<claude session name>&cwd=<path>&tmux=<tmux session>&sid=<uuid>
on open location theURL
	do shell script "echo \"$(date +%T) url=\" " & quoted form of theURL & " >> ~/Library/Logs/mainstem-jump.log"
	set parsed to do shell script "/usr/bin/python3 -c \"import sys,urllib.parse as u; p=u.urlparse(sys.argv[1]); d=dict(u.parse_qsl(p.query)); print('\\n'.join([p.netloc]+[d.get(k,'') for k in ('name','cwd','tmux','sid','tty','prompt')]))\" " & quoted form of theURL
	set {sKind, sName, sCwd, sTmux, sSid, sTty, sPrompt} to paragraphs of parsed
	if sKind is "start" then
		my startSession(sCwd, sPrompt)
		return
	end if
	set found to false
	tell application "iTerm"
		activate
		set byPath to {}
		repeat with w in windows
			repeat with t in tabs of w
				repeat with s in sessions of t
					set n to name of s
					set ty to ""
					try
						set ty to tty of s
					end try
					set p to ""
					try
						tell s to set p to variable named "session.path"
					end try
					if (sTty is not "" and ty is not "" and sTty contains ty) or (sTmux is not "" and n contains sTmux) or (sName is not "" and n contains sName) then
						select w
						select t
						select s
						set found to true
						exit repeat
					end if
					if sCwd is not "" and p is sCwd then set end of byPath to {w, t, s}
				end repeat
				if found then exit repeat
			end repeat
			if found then exit repeat
		end repeat
		if not found and (count of byPath) is 1 then
			set {w, t, s} to item 1 of byPath
			select w
			select t
			select s
			set found to true
		end if
		if not found then
			if (count of windows) is 0 then create window with default profile
			tell current window
				set newTab to (create tab with default profile)
				tell current session of newTab
					if sTmux is not "" then
						write text "tmux attach -t " & quoted form of sTmux
					else if sSid is not "" then
						write text "cd " & quoted form of sCwd & " && echo 'Session " & sName & " is running elsewhere. To take it over here: claude --resume " & sSid & "'"
					else
						write text "cd " & quoted form of sCwd
					end if
				end tell
			end tell
		end if
	end tell
	do shell script "echo \"$(date +%T) done found=" & found & "\" >> ~/Library/Logs/mainstem-jump.log"
end open location

-- ms://start?cwd=<dir under $HOME>&prompt=<text>: new iTerm2 tab, cd, start Claude with the prompt.
-- The URL never carries a command: only cwd and prompt, both validated and quoted here.
on startSession(sCwd, sPrompt)
	set homeDir to (do shell script "echo $HOME")
	if sCwd does not start with homeDir or sCwd contains ".." then
		do shell script "echo \"$(date +%T) start refused cwd=\" " & quoted form of sCwd & " >> ~/Library/Logs/mainstem-jump.log"
		return
	end if
	set cmd to "cd " & quoted form of sCwd & " && claude"
	if sPrompt is not "" then set cmd to cmd & " " & quoted form of sPrompt
	tell application "iTerm"
		activate
		if (count of windows) is 0 then create window with default profile
		tell current window
			set newTab to (create tab with default profile)
			tell current session of newTab to write text cmd
		end tell
	end tell
	do shell script "echo \"$(date +%T) started in \" " & quoted form of sCwd & " >> ~/Library/Logs/mainstem-jump.log"
end startSession
