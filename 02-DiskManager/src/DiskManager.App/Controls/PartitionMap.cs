using System;
using System.Collections.Generic;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace DiskManager.Controls
{
    public sealed class PartitionMapItem
    {
        public long StartBytes;
        public long SizeBytes;
        public string Label;
        public string Detail;
        public bool IsUnallocated;
        public bool IsSelected;
        public Brush Fill;
        public Brush TextBrush;
    }

    public sealed class PartitionMap : FrameworkElement
    {
        public static readonly DependencyProperty ItemsProperty = DependencyProperty.Register(
            nameof(Items), typeof(IEnumerable<PartitionMapItem>), typeof(PartitionMap),
            new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

        public static readonly DependencyProperty DiskSizeProperty = DependencyProperty.Register(
            nameof(DiskSize), typeof(long), typeof(PartitionMap),
            new FrameworkPropertyMetadata(0L, FrameworkPropertyMetadataOptions.AffectsRender));

        private readonly Typeface _typeface = new Typeface(new FontFamily("Microsoft YaHei UI, Segoe UI"), FontStyles.Normal, FontWeights.SemiBold, FontStretches.Normal);

        private sealed class Segment
        {
            public PartitionMapItem Item;
            public double X;
            public double Width;
        }

        public IEnumerable<PartitionMapItem> Items
        {
            get { return (IEnumerable<PartitionMapItem>)GetValue(ItemsProperty); }
            set { SetValue(ItemsProperty, value); }
        }

        public long DiskSize
        {
            get { return (long)GetValue(DiskSizeProperty); }
            set { SetValue(DiskSizeProperty, value); }
        }

        public PartitionMap()
        {
            Height = 46;
            MinHeight = 40;
            ClipToBounds = true;
            ToolTipService.SetShowDuration(this, 30000);
        }

        protected override void OnRender(DrawingContext drawingContext)
        {
            var segments = BuildSegments(ActualWidth);
            if (segments.Count == 0) return;

            var height = ActualHeight;
            if (height <= 1) return;

            const double gap = 2.5;
            var radius = 7.0;
            var pixelsPerDip = VisualTreeHelper.GetDpi(this).PixelsPerDip;

            foreach (var segment in segments)
            {
                var drawX = segment.X + (segment.X <= 0.01 ? 0 : gap / 2);
                var drawW = Math.Max(1.0, segment.Width - gap);
                if (drawX + drawW > ActualWidth) drawW = Math.Max(1.0, ActualWidth - drawX);

                var item = segment.Item;
                var rect = new Rect(drawX, 0, drawW, height);
                var fill = item.Fill ?? Brushes.DimGray;
                Pen pen = null;
                if (item.IsSelected)
                {
                    pen = new Pen(new SolidColorBrush(Color.FromArgb(235, 255, 246, 238)), 1.6);
                }
                else if (item.IsUnallocated)
                {
                    pen = new Pen(new SolidColorBrush(Color.FromArgb(70, 255, 235, 225)), 1) { DashStyle = DashStyles.Dash };
                }
                if (drawW < 2.5) pen = null;

                if (drawW >= 1.8)
                {
                    drawingContext.DrawRoundedRectangle(fill, pen, rect, Math.Min(radius, drawW / 2.0), Math.Min(radius, drawW / 2.0));
                }

                if (drawW >= 50 && item.Label != null)
                {
                    var text = new FormattedText(item.Label, CultureInfo.CurrentUICulture, FlowDirection.LeftToRight, _typeface, 12, item.TextBrush ?? Brushes.White, pixelsPerDip);
                    if (text.Width <= drawW - 12)
                    {
                        drawingContext.DrawText(text, new Point(drawX + (drawW - text.Width) / 2.0, height / 2.0 - text.Height / 2.0 - 0.5));
                    }
                }
            }
        }

        private List<Segment> BuildSegments(double width)
        {
            var result = new List<Segment>();
            var items = Items;
            var total = DiskSize;
            if (items == null || total <= 0 || width <= 1) return result;

            var visible = new List<PartitionMapItem>();
            foreach (var item in items)
            {
                if (item != null && item.SizeBytes > 0) visible.Add(item);
            }
            if (visible.Count == 0) return result;

            const double gap = 2.5;
            var drawable = width - gap * Math.Max(0, visible.Count - 1);
            if (drawable <= 4) return result;

            var raw = new double[visible.Count];
            var small = new bool[visible.Count];
            var minWidth = Math.Min(7.0, drawable / Math.Max(1, visible.Count));
            var fixedWidth = 0.0;
            var largeSize = 0L;
            for (var i = 0; i < visible.Count; i++)
            {
                raw[i] = visible[i].SizeBytes / (double)total * drawable;
                small[i] = raw[i] < minWidth && !visible[i].IsUnallocated;
                if (small[i]) fixedWidth += minWidth;
                else largeSize += visible[i].SizeBytes;
            }

            var available = drawable - fixedWidth;
            if (available <= 4 || largeSize <= 0)
            {
                // Too crowded to guarantee minimum widths; fall back to exact proportions.
                var cursor = 0.0;
                for (var i = 0; i < visible.Count; i++)
                {
                    var w = visible[i].SizeBytes / (double)total * drawable;
                    result.Add(new Segment { Item = visible[i], X = cursor, Width = w });
                    cursor += w + gap;
                }
                return result;
            }

            var x = 0.0;
            for (var i = 0; i < visible.Count; i++)
            {
                var w = small[i] ? minWidth : visible[i].SizeBytes / (double)largeSize * available;
                result.Add(new Segment { Item = visible[i], X = x, Width = w });
                x += w + gap;
            }
            return result;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            var item = HitTest(e.GetPosition(this));
            ToolTip = item == null ? null : (string.IsNullOrEmpty(item.Detail) ? item.Label : item.Detail);
        }

        protected override void OnMouseLeave(MouseEventArgs e)
        {
            base.OnMouseLeave(e);
            ToolTip = null;
        }

        private PartitionMapItem HitTest(Point point)
        {
            var segments = BuildSegments(ActualWidth);
            foreach (var segment in segments)
            {
                if (point.X >= segment.X && point.X <= segment.X + segment.Width) return segment.Item;
            }
            return null;
        }
    }
}
