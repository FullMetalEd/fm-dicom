"""
Runtime patch for pydicom 3.0.1 PIL features bug

This module applies a runtime fix for the missing PIL.features import
in pydicom 3.0.1's Pillow decoder.
"""

def apply_pydicom_patch():
    """Apply runtime patches for known pydicom issues"""
    try:
        # Fix PIL.features import bug in pydicom 3.0.1
        import pydicom.pixels.decoders.pillow as pillow_decoder

        # Check if the bug exists (features not imported)
        if not hasattr(pillow_decoder, 'features'):
            try:
                from PIL import features
                # Monkey patch the missing import
                pillow_decoder.features = features
                print("✅ Applied pydicom PIL.features patch")
            except ImportError:
                print("⚠️  Could not import PIL.features for patch")

    except ImportError:
        # pydicom not available or different version
        pass
    except Exception as e:
        print(f"⚠️  Could not apply pydicom patch: {e}")

# Apply patch when module is imported
apply_pydicom_patch()