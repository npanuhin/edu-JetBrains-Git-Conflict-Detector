#!/bin/bash

echo ">>> Setting up Git structure..."
echo

# Explanation: "&& ^"" is needed, since this executable gets deleted because we are switching branches

git checkout main
git branch -D branchA
git checkout -b branchB branchA_outdated && \
echo "It's dangerous to go alone! Take this." > file_in_root.txt && \
echo "This file is filled with content in both branches" > folder_in_root/empty_file.txt && \
echo "This file is modified in both branches" > folder_in_root/folder_nested/file_in_folders.txt && \
echo "This file is changed only on branch B" > folder_in_root/folder_nested/file_changed_only_on_branchB.txt && \
touch folder_in_root/folder_nested/created_file.txt && \
git rm folder_in_root/folder_nested/deleted_file.txt && \
git mv folder_in_root/folder_nested/renamed_file.txt folder_in_root/truly_renamed_file.txt  && \
git add folder_in_root file_in_root.txt && \
git commit --no-gpg-sign -m "New commit on branch \`branchB\` (stored only locally)" && \
git checkout main

echo
echo ">>> Setup complete"
