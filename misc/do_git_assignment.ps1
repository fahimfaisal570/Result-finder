$ErrorActionPreference = "Stop"

# Define variables
$repoName = "git-practice-ucc"
$userEmail = "ucc@example.com"
$userName = "UCC"

# Clean up if exists to prevent errors
if (Test-Path $repoName) {
    Remove-Item -Recurse -Force $repoName
}

# Task 2
mkdir $repoName -Force | Out-Null
cd $repoName
git init

# Configure local git user to avoid commit errors
git config user.email $userEmail
git config user.name $userName

# Task 3
mkdir src -Force | Out-Null
mkdir docs -Force | Out-Null
New-Item -ItemType File -Force -Path "src\utils.py" | Out-Null

$readmeText = @"
Project Title
UCC
This project is a simple python calculator.
"@
Set-Content -Path README.md -Value $readmeText

$mainText = @"
print('Name: UCC')
print('Date: 2026-04-02')
"@
Set-Content -Path src\main.py -Value $mainText

$descText = @"
Initial project description draft.
"@
Set-Content -Path docs\project-description.md -Value $descText

git add .
git commit -m "Initial commit: project structure and basic program"

# Rename branch to main
git branch -M main

# Task 4
Set-Content -Path .gitignore -Value "__pycache__/`n.env"
git add .gitignore
git commit -m "Add gitignore file"

# Task 5
git branch feature/calculator
git checkout feature/calculator

$utilsText = @"
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
"@
Set-Content -Path src\utils.py -Value $utilsText

$mainText2 = @"
from utils import add, subtract

print('Name: UCC')
print('Date: 2026-04-02')

print('5 + 3 =', add(5, 3))
print('5 - 3 =', subtract(5, 3))
"@
Set-Content -Path src\main.py -Value $mainText2

git add .
git commit -m "Add basic calculator functions"

# Task 6
git checkout main
git merge feature/calculator
git branch -d feature/calculator

# Task 8
# Commit 1
$readmeText2 = @"
# Python Calculator Project
**By:** UCC

This project is a simple calculator built to practice Git. We are learning how to branch, merge, and manage changes cleanly!
"@
Set-Content -Path README.md -Value $readmeText2
git add .
git commit -m "Improve README formatting"

# Commit 2
$utilsText2 = @"
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
"@
Set-Content -Path src\utils.py -Value $utilsText2

$mainText3 = @"
from utils import add, subtract, multiply

print('Name: UCC')
print('Date: 2026-04-02')

print('5 + 3 =', add(5, 3))
print('5 - 3 =', subtract(5, 3))
print('5 * 3 =', multiply(5, 3))
"@
Set-Content -Path src\main.py -Value $mainText3

git add .
git commit -m "Add multiply function"

# Commit 3
$descText2 = @"
# Complete Project Description
This repository serves as a practical assignment for the Git and GitHub module. 
It features a modular Python calculator with basic arithmetic operations.
"@
Set-Content -Path docs\project-description.md -Value $descText2
git add .
git commit -m "Update project-description.md"

# Task 9
git checkout -b feature/error-handling

$utilsText3 = @"
def add(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return "Error: arguments must be numbers"
    return a + b

def subtract(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return "Error: arguments must be numbers"
    return a - b

def multiply(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return "Error: arguments must be numbers"
    return a * b
"@
Set-Content -Path src\utils.py -Value $utilsText3
git add .
git commit -m "Add basic error handling to the calculator"

git checkout main
git merge feature/error-handling

Write-Host "All local Git configuration is complete!"
git log --oneline
