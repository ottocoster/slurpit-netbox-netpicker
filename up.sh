#!/bin/bash

# Function to check internet connectivity
check_internet() {
    # Define space-separated list of hosts
    hosts="8.8.8.8 1.1.1.1 google.com"
    timeout=2  # Timeout in seconds

    for host in $hosts; do
        if ping -c 1 -W "$timeout" "$host" >/dev/null 2>&1; then
            return 0  # Internet is available (0 = success in Bash)
        fi
    done
    return 1  # No internet connection (1 = failure in Bash)
}


# Function to handle Docker Compose operations
docker_compose_up() {    
    if check_internet; then
        docker compose pull
    else
        echo "No internet connection detected"
        echo "Skipping pull operation"
    fi
    
    echo "Starting containers..."
    docker compose up -d --build
}

# Main execution
docker_compose_up
