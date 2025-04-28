import os
import subprocess
import time
from pathlib import Path

os.system('clear')
print("=" * 42)
print("Created by Parsa in OPIran club https://t.me/OPIranClub")
print("Love Iran :)")
print("=" * 42)

# Ask user if they want to clean everything first
cleanup = input("Do you want to remove all existing configs and proxies? (y/n): ").strip().lower()
if cleanup == 'y':
    print("Cleaning up previous configurations...")
    for i in range(1, 13):
        os.system(f"sudo systemctl stop danted-warp{i} 2>/dev/null")
        os.system(f"sudo systemctl disable danted-warp{i} 2>/dev/null")
        os.system(f"sudo rm -f /etc/systemd/system/danted-warp{i}.service")
        os.system(f"sudo rm -f /etc/danted-multi/danted-warp{i}.conf")
        os.system(f"sudo wg-quick down wgcf{i} 2>/dev/null || sudo ip link delete wgcf{i} 2>/dev/null")
        os.system(f"sudo rm -f /etc/wireguard/wgcf{i}.conf")
        os.system(f"sudo rm -rf ~/warp-confs/warp{i}")
    os.system("sudo systemctl daemon-reexec")
    os.system("sudo modprobe -r wireguard || true")
    print("Cleanup completed. Continuing with fresh setup...\n")

print("Installing WireGuard and required packages...")
os.system("sudo apt update")
os.system("sudo apt install -y wireguard resolvconf curl jq dante-server unzip")

if not Path("/usr/local/bin/wgcf").exists():
    print("Installing wgcf...")
    os.system("curl -fsSL git.io/wgcf.sh | sudo bash")

os.makedirs("~/warp-confs", exist_ok=True)
os.chdir(os.path.expanduser("~/warp-confs"))

print("Generating 8 WARP configs...")
for i in range(1, 6):
    conf_path = f"/etc/wireguard/wgcf{i}.conf"
    if Path(conf_path).exists():
        print(f"  Config wgcf{i}.conf already exists, skipping.")
        continue

    os.makedirs(f"warp{i}", exist_ok=True)
    os.chdir(f"warp{i}")

    # Ensure no leftover wgcf-account exists
    if Path("wgcf-account.toml").exists():
        os.remove("wgcf-account.toml")

    os.system("wgcf register --accept-tos > /dev/null")
    os.system("wgcf generate")
    os.system(f"cp wgcf-profile.conf {conf_path}")

    ip_addr = f"172.16.0.{i+1}"
    table_id = 51820 + i
    os.system(f"sudo sed -i 's|Address = .*|Address = {ip_addr}/32|' {conf_path}")
    os.system(f"sudo sed -i '/\\[Interface\\]/a Table = {table_id}\\nPostUp = ip rule add from {ip_addr}/32 table {table_id}\\nPostDown = ip rule del from {ip_addr}/32 table {table_id}' {conf_path}")
    os.chdir("..")

print("Cleaning up existing WireGuard interfaces and module...")
os.system("for i in $(ip link show | grep wg | awk -F: '{print $2}' | tr -d ' '); do sudo wg-quick down $i 2>/dev/null || sudo ip link delete $i; done")
os.system("sudo modprobe -r wireguard || true")
os.system("sudo modprobe wireguard")

print("Bringing up interfaces...")
for i in range(1, 9):
    os.system(f"sudo systemctl enable --now wg-quick@wgcf{i}")

print("Setting up Dante SOCKS proxies...")
os.makedirs("/etc/danted-multi", exist_ok=True)
for i in range(1, 6):
    port = 1080 + i
    ip = f"172.16.0.{i+1}"
    conf_file = f"/etc/danted-multi/danted-warp{i}.conf"
    with open(conf_file, "w") as f:
        f.write(f"""logoutput: stderr
internal: 127.0.0.1 port = {port}
external: {ip}
user.privileged: root
user.unprivileged: nobody
clientmethod: none
socksmethod: none
client pass {{ from: 0.0.0.0/0 to: 0.0.0.0/0 }}
socks pass {{ from: 0.0.0.0/0 to: 0.0.0.0/0 }}
""")

    service_file = f"/etc/systemd/system/danted-warp{i}.service"
    with open(service_file, "w") as f:
        f.write(f"""[Unit]
Description=Dante SOCKS proxy warp{i}
After=network.target

[Service]
Type=simple
ExecStart=/usr/sbin/danted -f {conf_file}
Restart=on-failure

[Install]
WantedBy=multi-user.target
""")

    os.system("sudo systemctl daemon-reexec")
    os.system(f"sudo systemctl enable danted-warp{i}")
    os.system(f"sudo systemctl restart danted-warp{i}")
    time.sleep(1)

print("Checking public IPs via SOCKS proxies for uniqueness...")
all_unique = False
while not all_unique:
    os.system("sudo modprobe wireguard")
    ip_map = {}
    proxy_ips = {}
    all_unique = True
    print("Checking IPs:")
    for i in range(1, 6):
        # Restart corresponding Dante proxy first
        os.system(f"sudo systemctl restart danted-warp{i}")
        # Restart WireGuard interface
        os.system(f"sudo systemctl restart wg-quick@wgcf{i}")
        time.sleep(10)
        try:
            ip_raw = subprocess.check_output([
                "curl", "-s", "--socks5", f"127.0.0.1:{1080 + i}", "https://api.ipify.org"
            ]).decode().strip()
        except:
            ip_raw = "error"

        print(f"  wgcf{i} (SOCKS 127.0.0.1:{1080 + i}) → {ip_raw}")
        proxy_ips[i] = ip_raw
        if ip_raw in ip_map or ip_raw == "error":
            all_unique = False
        ip_map[ip_raw] = 1

    if not all_unique:
        choice = input("Some IPs are not unique. Do you want to try again? (y/n): ").strip().lower()
        if choice != 'y':
            print("Returning only proxies with unique IPs:")
            for i in range(1, 6):
                ip = proxy_ips[i]
                if ip_map[ip] == 1 and ip != "error":
                    print(f"  wgcf{i} → SOCKS5: 127.0.0.1:{1080 + i}  (IP: {ip})")
            break
        print("Restarting WireGuard and Dante services...")
        for i in range(1, 6):
            os.system(f"sudo wg-quick down wgcf{i} 2>/dev/null || sudo ip link delete wgcf{i} 2>/dev/null")
            os.system(f"sudo systemctl restart danted-warp{i}")
        print("Waiting 30 seconds before retry...")
        time.sleep(30)
        os.system("sudo modprobe -r wireguard || true")

print("\nSOCKS5 proxies (with unique public IPs):")
for i in range(1, 6):
    print(f"  wgcf{i} → 127.0.0.1:{1080 + i}")
