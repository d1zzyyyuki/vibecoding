using System.Windows;
using System.Windows.Media;

namespace DiskManager.ViewModels;

internal static class UiBrush
{
	public static Brush Get(string key)
	{
		try
		{
			Brush brush = ((Application.Current == null) ? null : (Application.Current.TryFindResource(key) as Brush));
			if (brush != null)
			{
				return brush;
			}
		}
		catch
		{
		}
		return Brushes.Gray;
	}
}
