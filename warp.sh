    #!/bin/bash

echo -e "\033[1;33m=========================================="
echo -e "Created by Parsa in OPIran club https://t.me/OPIranClub"
echo -e "Love Iran :)"
echo -e "==========================================\033[0m"

    set -e

    echo "Installing WireGuard and required packages..."
    sudo apt update
    sudo apt install -y wireguard resolvconf curl jq dante-server unzip

    echo "Installing wgcf if not available..."
    if ! command -v wgcf &> /dev/null; then
        curl -fsSL git.io/wgcf.sh | sudo bash
    fi

    echo "Creating config directory..."
    mkdir -p ~/warp-confs
    cd ~/warp-confs

    echo "Generating 12 WARP configs (if not already created)..."
    for i in {1..8}; do
        if [ -f "/etc/wireguard/wgcf$i.conf" ]; then
            echo "  Config wgcf$i.conf already exists, skipping."
            continue
        fi
        mkdir -p warp$i
        cd warp$i
        wgcf register --accept-tos > /dev/null
        wgcf generate
        cp wgcf-profile.conf /etc/wireguard/wgcf$i.conf

        ip_suffix=$((i + 1))
        ip_addr="172.16.0.$ip_suffix"
        table_id=$((51820 + i))

        sed -i "s|Address = .*|Address = $ip_addr/32|" /etc/wireguard/wgcf$i.conf
        sed -i "/\[Interface\]/a Table = $table_id\nPostUp = ip rule add from $ip_addr/32 table $table_id\nPostDown = ip rule del from $ip_addr/32 table $table_id" /etc/wireguard/wgcf$i.conf
        cd ..
    done

    echo "Cleaning up existing WireGuard interfaces and kernel module..."
    for i in $(ip link show | grep wg | awk -F: '{print $2}' | tr -d ' '); do
      sudo wg-quick down $i 2>/dev/null || sudo ip link delete $i
    done
    sudo modprobe -r wireguard || true
    sudo modprobe wireguard

    echo "Bringing up interfaces..."
    for i in {1..8}; do
        systemctl enable --now wg-quick@wgcf$i
    done

    echo "Setting up Dante SOCKS proxies for each config..."
    sudo mkdir -p /etc/danted-multi
    for i in {1..8}; do
        port=$((1080 + i))
        ip="172.16.0.$((i+1))"
        conf_file="/etc/danted-multi/danted-warp$i.conf"
        cat <<EOF | sudo tee $conf_file > /dev/null
logoutput: stderr
internal: 127.0.0.1 port = $port
external: $ip
user.privileged: root
user.unprivileged: nobody
clientmethod: none
socksmethod: none
client pass { from: 0.0.0.0/0 to: 0.0.0.0/0 }
socks pass { from: 0.0.0.0/0 to: 0.0.0.0/0 }
EOF

        service_file="/etc/systemd/system/danted-warp$i.service"
        cat <<EOL | sudo tee $service_file > /dev/null
[Unit]
Description=Dante SOCKS proxy warp$i
After=network.target

[Service]
Type=simple
ExecStart=/usr/sbin/danted -f $conf_file
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOL

        sudo systemctl daemon-reexec
        sudo systemctl enable danted-warp$i
		sudo systemctl restart danted-warp$i
		sleep 1
    done

    echo "Checking public IPs via SOCKS proxies for uniqueness..."
    all_unique=false
    while [ "$all_unique" = false ]; do
        sudo modprobe wireguard

        declare -A ip_map=()
        declare -A proxy_ips=()
        all_unique=true
        echo "Checking IPs:"
        for i in {1..8}; do
            sudo systemctl restart wg-quick@wgcf$i
            sleep 10
            ip="error"
            ip_raw=$(curl -s --socks5 127.0.0.1:$((1080 + i)) https://api.ipify.org || true)
            if [[ $ip_raw =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
                ip=$ip_raw
            fi
            echo "  wgcf$i (SOCKS 127.0.0.1:$((1080 + i))) → $ip"
            proxy_ips[$i]=$ip
            if [[ "${ip_map[$ip]}" || "$ip" == "error" ]]; then
                all_unique=false
            fi
            ip_map[$ip]=1
        done

        if [ "$all_unique" = false ]; then
            echo ""
            read -p "Some IPs are not unique. Do you want to try again? (y/n): " user_choice
            if [[ "$user_choice" != "y" ]]; then
                echo "Returning only proxies with unique IPs:"
                for i in {1..8}; do
                    ip=${proxy_ips[$i]}
                    if [[ "${ip_map[$ip]}" == "1" && "$ip" != "error" ]]; then
                        echo "  wgcf$i → SOCKS5: 127.0.0.1:$((1080 + i))  (IP: $ip)"
                    fi
                done
                exit 0
            fi

            echo "Restarting WireGuard interfaces..."
            for i in {1..8}; do
                if ip link show wgcf$i &> /dev/null; then
                    sudo wg-quick down wgcf$i || sudo ip link delete wgcf$i
                fi
            done

            echo "Waiting 30 seconds before retry..."
            sleep 30

            sudo modprobe -r wireguard || true
        fi
    done

    echo ""
    echo "SOCKS5 proxies (with unique public IPs):"
    for i in {1..8}; do
        echo "  wgcf$i → 127.0.0.1:$((1080 + i))"
    done
