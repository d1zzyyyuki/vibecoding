using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace DiskManager
{
    internal static class WindowFx
    {
        private const int DwmwaUseImmersiveDarkMode = 20;
        private const int DwmwaWindowCornerPreference = 33;

        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        public static void Apply(Window window, bool maximized)
        {
            try
            {
                var hwnd = new WindowInteropHelper(window).Handle;
                if (hwnd == IntPtr.Zero) return;
                var dark = 1;
                DwmSetWindowAttribute(hwnd, DwmwaUseImmersiveDarkMode, ref dark, sizeof(int));
                var corner = maximized ? 1 : 2;
                DwmSetWindowAttribute(hwnd, DwmwaWindowCornerPreference, ref corner, sizeof(int));
            }
            catch
            {
                // Older Windows builds do not support these attributes.
            }
        }
    }
}
