#!/bin/bash
# High-Speed VPS-to-Overleaf Bridge

echo "Locking Assets & Syncing to Overleaf..."

# 1. Pull latest Overleaf text edits to avoid merge conflicts
git pull origin master 

# 2. Stage only the finalized figures directory
git add Z_Final_Thesis_figures/*

# 3. Commit and Push
git commit -m "Auto-sync: Pushed updated vector graphics and TikZ circuits"
git push origin master

echo "Sync Complete. Assets are live in Overleaf."
