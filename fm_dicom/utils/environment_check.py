"""
Environment configuration checker for optimal Hyprland/Wayland integration.

This module checks the runtime environment and provides warnings/suggestions
for better integration with Wayland compositors like Hyprland.
"""

import os
import subprocess
import logging
from typing import List, Dict, Optional


class EnvironmentChecker:
    """Check environment configuration for optimal Qt/Wayland integration"""
    
    def __init__(self):
        self._desktop_environment = None
        self._compositor = None
        
    def get_desktop_environment(self) -> Optional[str]:
        """Detect the current desktop environment/compositor"""
        if self._desktop_environment is not None:
            return self._desktop_environment
            
        # Check for Wayland compositors
        if os.environ.get('WAYLAND_DISPLAY'):
            # Try to detect specific compositor
            if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
                self._desktop_environment = 'hyprland'
            elif 'sway' in os.environ.get('SWAYSOCK', ''):
                self._desktop_environment = 'sway'  
            elif os.environ.get('GNOME_DESKTOP_SESSION_ID'):
                self._desktop_environment = 'gnome-wayland'
            elif 'plasma' in os.environ.get('KDE_SESSION_VERSION', ''):
                self._desktop_environment = 'kde-wayland'
            else:
                self._desktop_environment = 'wayland-unknown'
        # Check for X11 environments
        elif os.environ.get('DISPLAY'):
            if os.environ.get('GNOME_DESKTOP_SESSION_ID'):
                self._desktop_environment = 'gnome-x11'
            elif 'plasma' in os.environ.get('KDE_SESSION_VERSION', ''):
                self._desktop_environment = 'kde-x11'
            else:
                self._desktop_environment = 'x11-unknown'
        else:
            self._desktop_environment = 'unknown'
            
        return self._desktop_environment
    
    def is_wayland(self) -> bool:
        """Check if running on Wayland"""
        de = self.get_desktop_environment()
        return de and ('wayland' in de or de == 'hyprland' or de == 'sway')
    
    def is_hyprland(self) -> bool:
        """Check if running on Hyprland specifically"""
        return self.get_desktop_environment() == 'hyprland'
    
    def check_qt_environment(self) -> Dict[str, any]:
        """Check Qt environment configuration"""
        issues = []
        recommendations = []
        warnings = []
        
        if not self.is_wayland():
            return {
                'issues': [],
                'recommendations': ['Environment appears to be X11, no Wayland-specific configuration needed'],
                'warnings': [],
                'score': 100
            }
        
        # Check Qt platform
        qt_platform = os.environ.get('QT_QPA_PLATFORM', '')
        if not qt_platform:
            issues.append("QT_QPA_PLATFORM not set")
            recommendations.append("Set QT_QPA_PLATFORM=wayland")
        elif 'wayland' not in qt_platform.lower():
            warnings.append(f"QT_QPA_PLATFORM={qt_platform} - consider 'wayland'")
        
        # Check platform theme
        qt_theme = os.environ.get('QT_QPA_PLATFORMTHEME', '')
        if not qt_theme:
            issues.append("QT_QPA_PLATFORMTHEME not set")
            if self.is_hyprland():
                recommendations.append("Set QT_QPA_PLATFORMTHEME=qt6ct for Hyprland")
            else:
                recommendations.append("Set QT_QPA_PLATFORMTHEME=gtk3 or qt6ct")
        
        # Check for Hyprland specific requirements
        if self.is_hyprland():
            # Check for common Hyprland Qt issues
            xcursor_theme = os.environ.get('XCURSOR_THEME')
            if not xcursor_theme:
                warnings.append("XCURSOR_THEME not set - cursor may not display correctly")
                
            xcursor_size = os.environ.get('XCURSOR_SIZE')
            if not xcursor_size:
                warnings.append("XCURSOR_SIZE not set - cursor size may be incorrect")
        
        # Check portal availability
        portal_available = self._check_portal_availability()
        if not portal_available:
            issues.append("XDG Desktop Portal not available")
            recommendations.append("Install xdg-desktop-portal and xdg-desktop-portal-gtk/kde")
        
        # Calculate score
        score = 100
        score -= len(issues) * 20
        score -= len(warnings) * 5
        score = max(0, score)
        
        return {
            'issues': issues,
            'recommendations': recommendations,
            'warnings': warnings,
            'score': score,
            'environment': self.get_desktop_environment()
        }
    
    def _check_portal_availability(self) -> bool:
        """Check if XDG Desktop Portal is available"""
        try:
            result = subprocess.run(
                ['dbus-send', '--session', '--dest=org.freedesktop.portal.Desktop', 
                 '--print-reply', '/org/freedesktop/portal/desktop', 
                 'org.freedesktop.DBus.Peer.Ping'],
                capture_output=True, timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def get_recommended_config(self) -> Dict[str, str]:
        """Get recommended environment variables for current setup"""
        config = {}
        
        if self.is_wayland():
            config['QT_QPA_PLATFORM'] = 'wayland'
            
            if self.is_hyprland():
                config['QT_QPA_PLATFORMTHEME'] = 'qt6ct'
                config['XCURSOR_THEME'] = 'Adwaita'  # Safe default
                config['XCURSOR_SIZE'] = '24'
            else:
                config['QT_QPA_PLATFORMTHEME'] = 'gtk3'
        
        return config
    
    def format_recommendations(self, check_result: Dict) -> str:
        """Format check results as user-friendly text"""
        lines = []
        
        env = check_result.get('environment', 'unknown')
        score = check_result.get('score', 0)
        
        lines.append(f"Environment: {env.title()}")
        lines.append(f"Configuration Score: {score}/100")
        lines.append("")
        
        if check_result['issues']:
            lines.append("🔴 Issues:")
            for issue in check_result['issues']:
                lines.append(f"  • {issue}")
            lines.append("")
        
        if check_result['warnings']:
            lines.append("🟡 Warnings:")
            for warning in check_result['warnings']:
                lines.append(f"  • {warning}")
            lines.append("")
        
        if check_result['recommendations']:
            lines.append("💡 Recommendations:")
            for rec in check_result['recommendations']:
                lines.append(f"  • {rec}")
            lines.append("")
        
        if score < 80:
            lines.append("For optimal file dialog integration, consider applying the recommendations above.")
        
        return "\n".join(lines)


# Global instance
_environment_checker = None

def get_environment_checker():
    """Get global environment checker instance"""
    global _environment_checker
    if _environment_checker is None:
        _environment_checker = EnvironmentChecker()
    return _environment_checker


def check_environment_on_startup(show_warnings=True) -> Dict:
    """Check environment on application startup"""
    checker = get_environment_checker()
    result = checker.check_qt_environment()
    
    if show_warnings and (result['issues'] or result['warnings']):
        logging.info("Environment check completed with issues")
        logging.info(checker.format_recommendations(result))
    elif result['score'] == 100:
        logging.debug("Environment check: optimal configuration detected")
    
    return result