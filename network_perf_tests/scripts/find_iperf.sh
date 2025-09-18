#!/bin/bash

# find_iperf.sh - Script to locate the iperf executable on macOS

# Function to find iperf3 executable
find_iperf() {
    # Check common installation paths
    local candidates=(
        "/usr/local/bin/iperf3"
        "/usr/bin/iperf3"
        "/usr/local/sbin/iperf3"
        "/usr/sbin/iperf3"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done

    # If not found, print an error message
    echo "iperf3 not found. Please install it or ensure it is in your PATH." >&2
    return 1
}

# Execute the function and capture the output
find_iperf