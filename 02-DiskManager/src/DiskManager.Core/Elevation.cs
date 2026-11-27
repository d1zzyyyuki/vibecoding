using System;
using System.Runtime.InteropServices;
using DiskManager.Core.Native;

namespace DiskManager.Core
{
    public static class Elevation
    {
        public static bool IsElevated()
        {
            var token = IntPtr.Zero;
            var elevationBuffer = IntPtr.Zero;
            try
            {
                if (!NativeMethods.OpenProcessToken(NativeMethods.GetCurrentProcess(), NativeMethods.TOKEN_QUERY, out token)) return false;
                elevationBuffer = Marshal.AllocHGlobal(4);
                Marshal.WriteInt32(elevationBuffer, 0);
                uint returned;
                if (!NativeMethods.GetTokenInformation(token, NativeMethods.TokenElevation, elevationBuffer, 4, out returned)) return false;
                return Marshal.ReadInt32(elevationBuffer) != 0;
            }
            catch
            {
                return false;
            }
            finally
            {
                if (elevationBuffer != IntPtr.Zero) Marshal.FreeHGlobal(elevationBuffer);
                if (token != IntPtr.Zero) NativeMethods.CloseHandle(token);
            }
        }
    }
}
