#!/usr/bin/env python3
import sys
import json
import subprocess
from pathlib import Path

# Default encoding settings
DEFAULT_PRESET = {
    'name': 'Default x264',
    'codec': 'libx264',
    'params': {
        'crf': 24,
        'preset': 'veryslow'
    }
}

# Global encoding settings
ENCODE_SETTINGS = {
    'output_suffix': '_done',    # Will be added before the extension
    'output_extension': '.mp4',  # New file extension
    'presets': [DEFAULT_PRESET], # Initialize with default preset
    'preset_file': '.presets.json',  # Name of the preset file
    'merged_audio_codec': 'aac'  # Audio codec used when merging tracks
}

def load_encoding_presets():
    """
    Load additional encoding presets from preset file if it exists
    """
    script_dir = Path(__file__).parent
    preset_file = script_dir / ENCODE_SETTINGS['preset_file']
    
    if not preset_file.exists():
        return False
        
    try:
        with open(preset_file, 'r') as f:
            content = f.read().strip()
            if not content:
                return False
            custom_presets = json.loads(content)
            if isinstance(custom_presets, list):
                ENCODE_SETTINGS['presets'].extend(custom_presets)
                return True
    except json.JSONDecodeError:
        return False
    except Exception as e:
        print(f"Warning: Error loading {ENCODE_SETTINGS['preset_file']}: {e}")
    return False

def get_track_info(video_file):
    """
    Extract track information from video file using ffprobe
    """
    try:
        # Run ffprobe command to get stream information in JSON format
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(video_file)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error processing {video_file}: {result.stderr}")
            return None
            
        return json.loads(result.stdout)
        
    except FileNotFoundError:
        print("Error: ffprobe not found. Please ensure ffmpeg is installed and in your PATH")
        return None
    except Exception as e:
        print(f"Error processing {video_file}: {str(e)}")
        return None

def get_audio_tracks(video_file):
    """
    Get list of audio tracks and their titles
    """
    info = get_track_info(video_file)
    if not info or 'streams' not in info:
        return []
    
    audio_tracks = []
    for stream in info['streams']:
        if stream.get('codec_type') == 'audio':
            track_id = len(audio_tracks)
            tags = stream.get('tags', {})
            title = tags.get('title', tags.get('handler_name', 'Untitled'))
            language = tags.get('language', 'unknown')
            audio_tracks.append({
                'id': track_id,
                'title': title,
                'language': language
            })
    return audio_tracks

def get_subtitle_tracks(video_file):
    """
    Get list of subtitle tracks and their titles
    """
    info = get_track_info(video_file)
    if not info or 'streams' not in info:
        return []
    
    subtitle_tracks = []
    for stream in info['streams']:
        if stream.get('codec_type') == 'subtitle':
            track_id = len(subtitle_tracks)
            tags = stream.get('tags', {})
            title = tags.get('title', tags.get('handler_name', 'Untitled'))
            language = tags.get('language', 'unknown')
            subtitle_tracks.append({
                'id': track_id,
                'title': title,
                'language': language
            })
    return subtitle_tracks

def is_video_file(file_path):
    """
    Check if the file is a video file using ffprobe
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',  # Select first video stream
            '-show_entries', 'stream=codec_type',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(file_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0 and 'video' in result.stdout.lower()
        
    except Exception:
        return False
    

def get_encoding_preset(cached_settings=None, file_index=0):
    """
    Ask user which encoding preset to use
    """
    if cached_settings and cached_settings['use_cache'] and 'encoding_preset' in cached_settings:
        return cached_settings['encoding_preset']
    
    # If we only have the default preset, use it without asking
    if len(ENCODE_SETTINGS['presets']) == 1:
        preset = ENCODE_SETTINGS['presets'][0]
        if file_index == 0:
            cached_settings['encoding_preset'] = preset
        return preset
    
    print("\nAvailable encoding presets:")
    for i, preset in enumerate(ENCODE_SETTINGS['presets']):
        params_str = ', '.join(f"{k}={v}" for k, v in preset.get('params', {}).items())
        print(f"[{i}] {preset['name']} ({preset['codec']}, {params_str})")
    
    while True:
        choice = input("\nSelect encoding preset [0]: ").strip() or "0"
        
        if choice.isdigit() and 0 <= int(choice) < len(ENCODE_SETTINGS['presets']):
            preset = ENCODE_SETTINGS['presets'][int(choice)]
            if file_index == 0:
                cached_settings['encoding_preset'] = preset
            return preset
        
        print("Invalid choice, please try again")

def encode_video(input_file, cached_settings=None, file_index=0):
    """
    Encode video file using ffmpeg with specified settings
    """
    try:
        input_path = Path(input_file)
        output_path = input_path.parent / f"{input_path.stem}{ENCODE_SETTINGS['output_suffix']}{ENCODE_SETTINGS['output_extension']}"
        
        # Initialize command configuration
        cmd_config = {
            'input': str(input_path),
            'output': str(output_path),
            'video_settings': ['-map', '0:v'],
            'audio_settings': [],
            'filter_complex': None
        }
        
        # Get audio tracks and ask for user input
        audio_tracks = get_audio_tracks(input_path)
        
        if audio_tracks:
            if cached_settings and cached_settings['use_cache']:
                choice = cached_settings['audio_choice']
                track_list = cached_settings['audio_tracks']
            else:
                print("\nAvailable audio tracks:")
                for track in audio_tracks:
                    print(f"[{track['id']}]: {track['title']} ({track['language']})")
                
                print("\nHow would you like to handle audio tracks?")
                print("[1] Include specific tracks [default]")
                print("[2] Merge specific tracks")
                
                choice = input("\nEnter your choice (1-2): ").strip() or "1"
                
                if file_index == 0:  # Store settings for first file
                    cached_settings['audio_choice'] = choice
                
                if choice == "1":
                    track_list = input("\nEnter space-separated track IDs to include (empty=all, '-'=none): ").strip()
                elif choice == "2":
                    track_list = input("\nEnter space-separated track IDs to merge: ").strip()
                
                if file_index == 0:  # Store settings for first file
                    cached_settings['audio_tracks'] = track_list

            if choice == "1":
                if track_list == '':
                    # Include all audio tracks
                    cmd_config['audio_settings'] = ['-map', '0:a', '-c:a', 'copy']
                elif track_list == '-':
                    # No audio tracks
                    cmd_config['audio_settings'] = ['-an']
                else:
                    # Specific tracks
                    track_ids = track_list.split()
                    cmd_config['audio_settings'] = []
                    for track_id in track_ids:
                        cmd_config['audio_settings'].extend([
                            '-map', f'0:a:{track_id}',
                            '-c:a', 'copy'
                        ])
            elif choice == "2":
                if track_list:
                    track_ids = track_list.split()
                    filter_parts = []
                    for i, track_id in enumerate(track_ids):
                        filter_parts.append(f'[0:a:{track_id}]')
                    filter_parts.append(f"amerge=inputs={len(track_ids)}[aout]")
                    
                    # Set the audio filter complex
                    if cmd_config['filter_complex']:
                        cmd_config['filter_complex'] = f"{cmd_config['filter_complex']};{''.join(filter_parts)}"
                    else:
                        cmd_config['filter_complex'] = ''.join(filter_parts)
                    
                    # Set audio mapping and encoding
                    cmd_config['audio_settings'] = [
                        '-map', '[aout]',
                        '-c:a', ENCODE_SETTINGS['merged_audio_codec']
                    ]
        
        else:
            # No audio tracks found
            cmd_config['audio_settings'] = ['-an']
        
        # Handle subtitle tracks
        subtitle_tracks = get_subtitle_tracks(input_path)
        selected_subtitle = None
        should_reencode = False
        
        if subtitle_tracks:
            if cached_settings and cached_settings['use_cache']:
                sub_choice = str(cached_settings['subtitle_track']) if cached_settings['subtitle_track'] is not None else ""
            else:
                print("\nAvailable subtitle tracks:")
                for track in subtitle_tracks:
                    print(f"[{track['id']}]: {track['title']} ({track['language']})")
                
                sub_choice = input("\nEnter subtitle track ID to burn into video (empty=none): ").strip()
                
                if file_index == 0:  # Store settings for first file
                    cached_settings['subtitle_track'] = int(sub_choice) if sub_choice.isdigit() else None

            if sub_choice:
                try:
                    sub_id = int(sub_choice)
                    selected_subtitle = next((track for track in subtitle_tracks if track['id'] == sub_id), None)
                    if selected_subtitle:
                        should_reencode = True  # Force reencoding if burning subtitles
                        sub_path = cmd_config['input'].replace('\\', '\\\\').replace(':', '\\:')
                        if cmd_config['filter_complex']:
                            current_filter = cmd_config['filter_complex']
                            subtitle_filter = f"[0:v]subtitles='{sub_path}':si={sub_id}[vout]"
                            cmd_config['filter_complex'] = f"{current_filter};{subtitle_filter}"
                            cmd_config['video_settings'] = ['-map', '[vout]'] + cmd_config['video_settings'][2:]
                        else:
                            cmd_config['filter_complex'] = f"[0:v]subtitles='{sub_path}':si={sub_id}[vout]"
                            cmd_config['video_settings'] = ['-map', '[vout]'] + cmd_config['video_settings'][2:]
                except ValueError:
                    print("Invalid subtitle track ID, proceeding without subtitles")
        
        # Ask about reencoding if no subtitle was selected
        if not should_reencode:
            if cached_settings and cached_settings['use_cache']:
                should_reencode = cached_settings['should_reencode']
            else:
                reencode = input("\nDo you want to reencode the video? (y/N): ").strip().lower()
                should_reencode = reencode == 'y'
                if file_index == 0:
                    cached_settings['should_reencode'] = should_reencode
        
        # Get encoding preset and resolution if reencoding
        if should_reencode:
            # Get encoding preset
            preset = get_encoding_preset(cached_settings, file_index)
            
            # Update video settings with chosen preset
            cmd_config['video_settings'].extend([
                '-c:v', preset['codec']
            ])
            
            # Add all parameters from the preset
            for key, value in preset['params'].items():
                cmd_config['video_settings'].extend([f'-{key}', str(value)])
            
            # Handle resolution
            if cached_settings and cached_settings['use_cache']:
                res_choice = str(cached_settings['target_height']) if cached_settings['target_height'] is not None else ""
            else:
                res_choice = input("\nEnter target vertical resolution (720, 1080, etc.) or leave empty to keep original: ").strip()
                if file_index == 0:
                    cached_settings['target_height'] = int(res_choice) if res_choice.isdigit() else None
            
            if res_choice and res_choice.isdigit():
                height = int(res_choice)
                scale_filter = f"scale=-1:{height}"
                
                if cmd_config['filter_complex']:
                    # Handle both audio merge and scaling
                    if '[aout]' in cmd_config['filter_complex']:
                        # We have an audio merge filter, add video scaling in parallel
                        audio_filter = cmd_config['filter_complex']
                        video_filter = f"[0:v]{scale_filter}[vout]"
                        cmd_config['filter_complex'] = f"{audio_filter};{video_filter}"
                        cmd_config['video_settings'] = ['-map', '[vout]'] + cmd_config['video_settings'][2:]
                    else:
                        # We have a subtitle filter, add scaling after it
                        cmd_config['filter_complex'] = cmd_config['filter_complex'].replace('[vout]', f'[vtmp];[vtmp]{scale_filter}[vout]')
                else:
                    # Just scaling
                    cmd_config['filter_complex'] = f"[0:v]{scale_filter}[vout]"
                    cmd_config['video_settings'] = ['-map', '[vout]'] + cmd_config['video_settings'][2:]
        
        # If not reencoding, modify settings to copy video stream
        if not should_reencode:
            cmd_config['video_settings'] = ['-map', '0:v', '-c:v', 'copy']
        
        # Build final ffmpeg command
        cmd = ['ffmpeg', '-i', cmd_config['input']]
        
        if cmd_config['filter_complex']:
            cmd.extend(['-filter_complex', cmd_config['filter_complex']])
        
        cmd.extend(cmd_config['video_settings'])
        cmd.extend(cmd_config['audio_settings'])
        cmd.append(cmd_config['output'])
        
        # Print encoding information
        print(f"\nEncoding: {input_path}")
        print(f"Output to: {output_path}")
        print("Settings:")
        if should_reencode:
            print(f"  Codec: {preset['codec']}")
            for key, value in preset['params'].items():
                print(f"  {key}: {value}")
        else:
            print("  Video: Copy (no reencoding)")
        if selected_subtitle:
            print(f"  Burning subtitle track: [{selected_subtitle['id']}] {selected_subtitle['title']}")
        print("\nEncoding in progress...")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error encoding {input_file}: {result.stderr}")
            return False
            
        print("Encoding completed successfully!")
        return True
        
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please ensure ffmpeg is installed and in your PATH")
        return False
    except Exception as e:
        print(f"Error encoding {input_file}: {str(e)}")
        return False

def main():
    # Load custom encoding presets if available
    load_encoding_presets()
    
    # Check if files were provided as arguments
    if len(sys.argv) < 2:
        print("Usage: Drop video files onto this script or provide them as arguments")
        return
    
    # Settings cache for batch processing
    cached_settings = {
        'use_cache': False,
        'audio_choice': None,
        'audio_tracks': None,
        'subtitle_track': None,
        'should_reencode': False,
        'target_height': None,
        'encoding_preset': None
    }
    
    # Process each file
    for i, file_path in enumerate(sys.argv[1:]):
        path = Path(file_path)
        
        if not path.exists():
            print(f"Error: File not found: {file_path}")
            continue
            
        if not path.is_file():
            print(f"Error: Not a file: {file_path}")
            continue
        
        # Validate if it's a video file
        if not is_video_file(path):
            print(f"Error: Not a valid video file: {file_path}")
            continue
        
        # If this is not the first file and we have cached settings, ask if user wants to use them
        if i == 0:
            encode_video(path, cached_settings, i)
            if len(sys.argv[1:]) > 1:  # If there are more files
                print("\nMultiple files detected.")
                use_same = input("Do you want to use the same settings for all remaining files? (y/N): ").strip().lower()
                cached_settings['use_cache'] = use_same == 'y'
        else:
            if cached_settings['use_cache']:
                print(f"\nProcessing {path} with same settings...")
            encode_video(path, cached_settings, i)
        
        print("\n" + "="*50 + "\n")
    
    # Add prompt to prevent auto-closing
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
