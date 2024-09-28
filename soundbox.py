import os
import struct
import crcmod
import sys  # To handle command-line arguments

# Display the information line
print("Soundbox Flash tools thijsnl 2024 v0.1")

# Initialize the CRC-16-CCITT function (0x1021 polynomial, initial value 0x0000)
crc16_ccitt = crcmod.mkCrcFun(0x11021, initCrc=0x0000, xorOut=0x0000, rev=False)

# Initialize the CRC-16-XMODEM function for data CRC check (0x1021 polynomial, initCrc 0x0000, xorOut=0x0000)
crc16_xmodem = crcmod.mkCrcFun(0x11021, initCrc=0x0000, xorOut=0x0000, rev=False)

# Function to parse a single entry (32 bytes)
def parse_entry(entry_data):
    # Unpack the first part of the entry: 2 CRCs (header & data), offset, size, type, unknown1
    header_crc, data_crc, offset, size, type_flag, unknown1 = struct.unpack('<H H I I B 3s', entry_data[:16])
    
    # Extract the file/directory name and remove null termination
    name = entry_data[16:32].split(b'\x00', 1)[0].decode('utf-8')
    
    # Interpret the type flag
    entry_type = 'File' if type_flag == 0x02 else 'Directory' if type_flag == 0x03 else 'Unknown'
    
    return {
        'HeaderCRC': header_crc,
        'DataCRC': data_crc,
        'Offset': offset,
        'Size': size,
        'Type': entry_type,
        'Name': name,
        'Unknown1_bytes': unknown1,
        'EntryData': entry_data[2:]  # The 30 bytes after the header CRC (for CRC check)
    }

# Function to calculate and verify the header CRC
def verify_header_crc(entry):
    # Calculate the CRC over the 30 bytes following the header CRC (entry['EntryData'])
    calculated_crc = crc16_ccitt(entry['EntryData'])
    
    # Compare the calculated CRC with the stored header CRC
    if calculated_crc == entry['HeaderCRC']:
        return "Header CRC OK"
    else:
        return f"Header CRC Mismatch (Calculated CRC: 0x{calculated_crc:04X}, Expected CRC: 0x{entry['HeaderCRC']:04X})"

# Function to calculate and verify the data CRC
def verify_data_crc(entry, data):
    # Extract data from 'Offset' and 'Size' fields
    offset = entry['Offset']
    size = entry['Size']
    file_data = data[offset:offset + size]
    
    # Calculate the data CRC using CRC-16-XMODEM over the file data
    calculated_data_crc = crc16_xmodem(file_data)
    
    # Compare the calculated data CRC with the stored DataCRC
    if calculated_data_crc == entry['DataCRC']:
        return "Data CRC OK"
    else:
        return f"Data CRC Mismatch (Calculated CRC: 0x{calculated_data_crc:04X}, Expected CRC: 0x{entry['DataCRC']:04X})"

# Function to read and parse the binary file
def read_bin_file(file_path):
    entries = []
    crc_pairs = set()  # To track unique CRC pairs (header + data CRCs)
    
    with open(file_path, 'rb') as f:
        data = f.read()
        entry_size = 32
        num_entries = len(data) // entry_size
        
        for i in range(num_entries):
            entry_data = data[i * entry_size:(i + 1) * entry_size]
            entry = parse_entry(entry_data)
            
            # Check for duplicate header and data CRC pairs
            crc_pair = (entry['HeaderCRC'], entry['DataCRC'])
            if crc_pair in crc_pairs:
                print(f"Warning: Duplicate CRC pair found (HeaderCRC: 0x{entry['HeaderCRC']:04X}, DataCRC: 0x{entry['DataCRC']:04X})")
            else:
                crc_pairs.add(crc_pair)
            
            # Add each entry to the list
            entries.append(entry)
            
            # Check if unknown1 equals 0xFF0100, indicating the last entry
            if entry['Unknown1_bytes'] == b'\xFF\x01\x00':
                print("Last item found based on unknown1 == 0xFF0100. Stopping the process.")
                break

    # Print the entries with CRC check results in the original order
    for i, entry in enumerate(entries):
        header_crc_status = verify_header_crc(entry)  # Perform header CRC check
        data_crc_status = verify_data_crc(entry, data)  # Perform data CRC check
        print(f"Entry {i + 1}: HeaderCRC=0x{entry['HeaderCRC']:04X}, DataCRC=0x{entry['DataCRC']:04X}, Offset={entry['Offset']}, Size={entry['Size']}, Type={entry['Type']}, Name={entry['Name']}, {header_crc_status}, {data_crc_status}")
    
    return entries, data

# Function to extract files based on parsed entries
def extract_files(entries, data, output_dir):
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for entry in entries:
        if entry['Type'] == 'File':
            # Extract file data based on offset and size
            offset = entry['Offset']
            size = entry['Size']
            file_data = data[offset:offset + size]

            # Create the output file path
            file_path = os.path.join(output_dir, entry['Name'])
            
            # Write the file data to the output path
            with open(file_path, 'wb') as out_file:
                out_file.write(file_data)
                print(f"Extracted file: {entry['Name']} (Size: {entry['Size']} bytes)")

# Main function
if __name__ == '__main__':
    # Check if a filename is provided as an argument
    if len(sys.argv) < 2:
        print("Usage: python soundbox.py <bin_file> [-e]")
        sys.exit(1)
    
    # Get the binary file path from the first argument
    bin_file_path = sys.argv[1]
    
    # Output directory for extracted files
    output_directory = 'soundbox'

    # Read and parse the binary file
    entries, data = read_bin_file(bin_file_path)

    # Check if '-e' argument is present to trigger file extraction
    if '-e' in sys.argv:
        # Extract files into the soundbox directory
        extract_files(entries, data, output_directory)
    else:
        print("File extraction skipped. Use '-e' argument to enable extraction.")
