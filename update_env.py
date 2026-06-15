import os

env_path = "/Users/mac/Downloads/CREATOR FORGE/backend/.env"
lines = []
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        lines = f.readlines()

new_lines = []
for line in lines:
    if line.startswith("GOOGLE_EMAIL="):
        new_lines.append("GOOGLE_EMAIL=creatorforgeweb@gmail.com\n")
    elif line.startswith("GOOGLE_APP_PASSWORD="):
        new_lines.append("GOOGLE_APP_PASSWORD=,,,,,, Upworkproject\n")
    else:
        new_lines.append(line)

with open(env_path, "w") as f:
    f.writelines(new_lines)

print("Updated .env with Google credentials.")
