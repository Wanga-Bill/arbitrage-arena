import time
import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    logging.info("Starting Arbitrage Arena continuous alert engine daemon...")
    interval = 60  # Check every 60 seconds
    
    try:
        while True:
            logging.info("Checking for live arbitrage opportunities...")
            # Execute main.py alert engine run
            result = subprocess.run([sys.executable, "main.py"], capture_output=False)
            
            if result.returncode != 0:
                logging.warning(f"Alert engine exited with non-zero code: {result.returncode}")
                
            logging.info(f"Sleeping for {interval} seconds before next check...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        logging.info("Continuous alert engine daemon stopped by user.")
    except Exception as e:
        logging.error(f"Daemon encountered a fatal error: {e}")

if __name__ == "__main__":
    main()
