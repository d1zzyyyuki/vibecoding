using System;
using System.Windows;
using System.Windows.Media;

namespace DiskManager.Controls
{
    public sealed class UsageBar : FrameworkElement
    {
        public static readonly DependencyProperty PercentProperty = DependencyProperty.Register(
            nameof(Percent), typeof(double), typeof(UsageBar),
            new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.AffectsRender));

        public static readonly DependencyProperty TrackBrushProperty = DependencyProperty.Register(
            nameof(TrackBrush), typeof(Brush), typeof(UsageBar),
            new FrameworkPropertyMetadata(Brushes.Transparent, FrameworkPropertyMetadataOptions.AffectsRender));

        public static readonly DependencyProperty FillBrushProperty = DependencyProperty.Register(
            nameof(FillBrush), typeof(Brush), typeof(UsageBar),
            new FrameworkPropertyMetadata(Brushes.White, FrameworkPropertyMetadataOptions.AffectsRender));

        public double Percent
        {
            get { return (double)GetValue(PercentProperty); }
            set { SetValue(PercentProperty, value); }
        }

        public Brush TrackBrush
        {
            get { return (Brush)GetValue(TrackBrushProperty); }
            set { SetValue(TrackBrushProperty, value); }
        }

        public Brush FillBrush
        {
            get { return (Brush)GetValue(FillBrushProperty); }
            set { SetValue(FillBrushProperty, value); }
        }

        protected override void OnRender(DrawingContext drawingContext)
        {
            var width = ActualWidth;
            var height = ActualHeight;
            if (width <= 0 || height <= 0) return;

            var radius = height / 2.0;
            drawingContext.DrawRoundedRectangle(TrackBrush, null, new Rect(0, 0, width, height), radius, radius);

            var percent = Math.Max(0, Math.Min(100, Percent));
            var fillWidth = width * percent / 100.0;
            if (fillWidth <= 0.4) return;
            fillWidth = Math.Max(fillWidth, 2);
            if (fillWidth > width) fillWidth = width;
            var fillRadius = Math.Min(radius, fillWidth / 2.0);
            drawingContext.DrawRoundedRectangle(FillBrush, null, new Rect(0, 0, fillWidth, height), fillRadius, fillRadius);
        }
    }
}
