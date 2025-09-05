#!/bin/bash

# Install Homebrew if it's not already installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew is already installed."
fi

# Install iperf3
if ! command -v iperf3 &> /dev/null; then
    echo "iperf3 not found. Installing iperf3..."
    brew install iperf3
else
    echo "iperf3 is already installed."
fi

# Install other dependencies if needed
# Add any additional dependencies here, for example:
# pip install -r requirements.txt

echo "All dependencies are installed."