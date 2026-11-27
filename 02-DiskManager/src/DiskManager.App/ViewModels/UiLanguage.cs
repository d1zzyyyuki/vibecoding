namespace DiskManager.ViewModels
{
    public static class UiLanguage
    {
        public static bool English { get; set; }

        public static string T(string chinese, string english)
        {
            return English ? english : chinese;
        }
    }
}
