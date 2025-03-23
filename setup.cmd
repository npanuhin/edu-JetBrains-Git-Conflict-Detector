@echo off

echo ^>^>^> Setting up Git structure...
echo:

rem Explanation: "&& ^"" is needed, since this executable gets deleted because we are switching branches

git checkout main
git branch -D branchA
git checkout -b branchB branchA_outdated && ^
echo It's dangerous to go alone! Take this. > file.txt && ^
git add file.txt && ^
git commit --no-gpg-sign -m "New commit on branch `branchB`" && ^
git checkout main

echo:
echo ^>^>^> Setup complete
