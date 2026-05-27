import os

brain_dir = r"C:\Users\Ucc\.gemini\antigravity\brain"
print(f"Brain dir subdirectories: {os.listdir(brain_dir)}")

curr_conv = os.path.join(brain_dir, "0a4b941b-a029-47d3-bce3-729459e1cc0c")
if os.path.exists(curr_conv):
    print(f"Current conversation dir exists! Listing files:")
    for root, dirs, files in os.walk(curr_conv):
        for f in files:
            print(f"  {os.path.join(root, f)}")
else:
    print("Current conversation dir does not exist under that exact name!")
