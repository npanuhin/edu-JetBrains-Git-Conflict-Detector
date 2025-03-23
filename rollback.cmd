@echo off

echo ^>^>^> Resetting repository to original state...
echo:

rem Explanation: "&& ^"" is needed, since this executable gets deleted because we are switching branches

git checkout main
git branch -D branchB
git checkout -b branchA origin/branchA && ^
git checkout main

echo:
echo ^>^>^> Rollback complete
