#!/usr/bin/env python3
import time
import random
from prometheus_client import start_http_server, Gauge, Counter

# Create metrics
cpu_usage = Gauge('demo_cpu_usage_percent', 'Demo CPU usage', ['host'])
memory_usage = Gauge('demo_memory_usage_percent', 'Demo memory usage', ['host'])
http_requests = Counter('demo_http_requests_total', 'Demo HTTP requests', ['service', 'status'])
error_rate = Gauge('demo_error_rate', 'Demo error rate', ['service'])

# Track spike timing
spike_cycle = 0
spike_active = False
start_cycle = 0

def generate_metrics():
    """Generate realistic metric values with periodic spikes"""
    global spike_cycle, spike_active, start_cycle
    
    hosts = ['web-1', 'web-2', 'db-1']
    services = ['api', 'frontend', 'backend']
    
    print("Demo metrics generator started")
    print("💡 CPU will spike above 90% for 6 minutes to trigger alerts")
    print("🔄 Metrics updating every 15 seconds...")
    
    while True:
        spike_cycle += 1
        
        # Spike for 24 cycles (6 min), normal for 8 cycles (2 min) = 32 cycle total
        cycle_position = spike_cycle % 32
        
        if cycle_position == 1:
            spike_active = True
            print("\n🔥 SPIKE INITIATED - CPU will exceed 90% threshold for 6 minutes!")
        elif cycle_position == 25:
            spike_active = False
            print("\n✅ Spike ended - CPU back to normal for 2 minutes\n")
        
        # CPU usage - with controlled spikes
        for i, host in enumerate(hosts):
            if spike_active:
                # During spike: all hosts high, but web-1 highest
                if host == 'web-1':
                    value = random.uniform(92, 98)  # Guaranteed above 90% threshold
                else:
                    value = random.uniform(91, 95)
                print(f"  - {host}: CPU at {value:.1f}% (ALERT THRESHOLD!)")
            else:
                # Normal operation
                base_cpu = 20 + (i * 15)  # web-1=20%, web-2=35%, db-1=50%
                value = random.uniform(base_cpu - 5, base_cpu + 5)
            
            cpu_usage.labels(host=host).set(value)
        
        # Memory usage - slowly increasing then resetting
        for i, host in enumerate(hosts):
            base_mem = 50 + (spike_cycle % 20) * 2  # Slowly increases
            memory_usage.labels(host=host).set(base_mem + random.uniform(-5, 5))
        
        # HTTP requests
        for service in services:
            http_requests.labels(service=service, status='200').inc(random.randint(50, 200))
            if random.random() > 0.8:
                http_requests.labels(service=service, status='500').inc(random.randint(1, 10))
        
        # Error rates
        for service in services:
            error_rate.labels(service=service).set(random.uniform(0.5, 3.5))
        
        time.sleep(15)

if __name__ == '__main__':
    # Start metrics server
    start_http_server(8000)
    print("Prometheus Metrics Server Running on :8000")
    print("="*60)
    
    # Start generating metrics
    try:
        generate_metrics()
    except KeyboardInterrupt:
        print("\nShutting down...")