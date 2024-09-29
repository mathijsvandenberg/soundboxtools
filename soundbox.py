import os
import struct
import crcmod
import sys  # To handle command-line arguments

# Display the information line
print("Soundbox Flash tools thijsnl 2024 v0.2")

# Initialize the CRC-16-CCITT function (0x1021 polynomial, initial value 0x0000)
crc16_ccitt = crcmod.mkCrcFun(0x11021, initCrc=0x0000, xorOut=0x0000, rev=False)

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

    # Hack because the only directory needs to be truncated by 32 bytes to get a proper CRC returned.
    if (entry['Type'] == 'Directory'):
        size -= 32;

    file_data = data[offset:offset + size]
    
    # Calculate the data CRC using CRC-16-XMODEM over the file data
    calculated_data_crc = crc16_ccitt(file_data)
    
    # Compare the calculated data CRC with the stored DataCRC
    if calculated_data_crc == entry['DataCRC']:
        return "Data CRC OK"
    else:
        return f"Data CRC Mismatch (Calculated CRC: 0x{calculated_data_crc:04X}, Expected CRC: 0x{entry['DataCRC']:04X})"

# Function to read and parse the binary file
def read_bin_file(file_path):
    entries = []
    
    with open(file_path, 'rb') as f:
        data = f.read()
        entry_size = 32
        num_entries = len(data) // entry_size
        
        for i in range(num_entries):
            entry_data = data[i * entry_size:(i + 1) * entry_size]
            entry = parse_entry(entry_data)
            
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

        if (header_crc_status != "Header CRC OK" or data_crc_status != "Data CRC OK"):
            print("CRC Error! Abort!")
            exit();

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

# Function to pad file data to be a multiple of 16 bytes
def pad_to_multiple_of_16(file_data):
    padding_needed = (16 - (len(file_data) % 16)) % 16  # Calculate how much padding is needed
    return file_data + b'\xFF' * padding_needed  # Append padding bytes


# Function to pack files back into the binary format
def pack_files(output_bin_file, input_dir):
    entries = []
    offset = 32 * (len(os.listdir(input_dir)) + 1)  # Start after all the headers and the directory entry
    binary_data = b''
    file_list = sorted(os.listdir(input_dir))  # Sorted list of files in the directory
    num_files = len(file_list)


    # Iterate through all files in the soundbox directory
    for i, file_name in enumerate(file_list):
        file_path = os.path.join(input_dir, file_name)
        if os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                file_data = f.read()
                size = len(file_data)

                # Pad the file data to a multiple of 16 bytes
                file_data_padded = pad_to_multiple_of_16(file_data)
                size_padded = len(file_data_padded)
                

            # Calculate data CRC using CRC-16-CCITT
            data_crc = crc16_ccitt(file_data)

            # Create header entry
            entry_type = 0x02  # File type

            # Set unknown1 to b'\xFF\x01\x00' for the last file
            unknown1 = b'\xFF\x01\x00' if i == num_files - 1 else b'\xFF\x00\x00'

            entry_name = (file_name.encode('utf-8') + b'\x00').ljust(16, b'\xFF')[:16]  # Zero-padded file name (16 bytes)
            
            # Header without header CRC for the calculation
            header_data = struct.pack('<H I I B 3s 16s', data_crc, offset, size, entry_type, unknown1, entry_name)
            
            # Calculate header CRC using CRC-16-CCITT over the 30-byte header data
            header_crc = crc16_ccitt(header_data)
            
            # Full entry with CRCs
            entry = struct.pack('<H', header_crc) + header_data
            entries.append(entry)

            
            # Append the file data and update offset for the next file
            binary_data += file_data_padded
            offset += size_padded

    # Make the initial directory entry
    entry_name = ("test_dir".encode('utf-8') + b'\x00').ljust(16, b'\xFF')[:16]
    data_crc = crc16_ccitt(b''.join(entries) + binary_data)
    header_data = struct.pack('<H I I B 3s 16s', data_crc, 0x20, offset, 0x03, b'\xFF\x00\x00', entry_name)
    header_crc = crc16_ccitt(header_data)
    entry = struct.pack('<H', header_crc) + header_data
    entries.insert(0,entry)
    offset += 32

    # Write the packed binary data to the output file
    with open(output_bin_file, 'wb') as out_bin:
        for entry in entries:
            out_bin.write(entry)
        out_bin.write(binary_data)

    print(f"Packed files into {output_bin_file}.")

# Main function
if __name__ == '__main__':
    # Check if a filename is provided as an argument
    if len(sys.argv) < 2:
        print("Usage: python3 soundbox.py <bin_file> [-e]")
        sys.exit(1)
    
    # Get the binary file path from the first argument
    bin_file_path = sys.argv[1]
    
    # Output directory for extracted files
    output_directory = 'soundbox'



    # Check if '-e' argument is present to trigger file extraction
    if '-e' in sys.argv:

        # Read and parse the binary file
        entries, data = read_bin_file(bin_file_path)

        # Extract files into the soundbox directory
        extract_files(entries, data, output_directory)
    elif '-p' in sys.argv:
        # Pack files from the soundbox directory
        pack_files(bin_file_path, output_directory)
    else:
        # Read and parse the binary file
        entries, data = read_bin_file(bin_file_path)
        print("File extraction skipped. Use '-e' argument to enable extraction.")
