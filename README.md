# Parrot Pot Home Assistant Integration

## Overview

The Parrot Pot home assistant integration allows you to easily monitor your Parrot Pot from your home automation system. This integration provides access to moisture levels, watering level, and more.

## Features
- battery
- Temperature
- Moisture
- Light
- Water Level

## Installation

### Option 1: Install via HACS (Recommended)
1. Ensure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance
2. Open HACS → Integrations
3. Click the three dots menu (⋮) in the top-right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/JacVid/ParrotPot`
5. Select "Integration" as the category and click Add
6. Search for "Parrot Pot" in HACS and click on it
7. Click "Download" to install the integration
8. Restart Home Assistant
9. Add integration via Settings → Devices & Services → Add Integration → Parrot Pot (you need the MAC address of your pot)

### Option 2: Manual Installation
1. Copy the `parrotpot` folder to `/custom_components/` of your Home Assistant directory via SSH or SMB
2. Restart Home Assistant
3. Add integration via Settings → Devices & Services → Add Integration → Parrot Pot (you need the MAC address of your pot)

## Usage
Once set up, you can access your Parrot Pot directly from your Home Assistant dashboard, where you can view stats of your pot (refresh every 60 mn for batteries).

## Troubleshooting
- Ensure that your Parrot Pot is not connected to your smartphone.
- Check Home Assistant logs for any errors related to the integration.+

## Result
<img width="992" height="865" alt="image" src="https://github.com/user-attachments/assets/226e512e-5cb3-4856-bc82-957e6a847f7d" />
