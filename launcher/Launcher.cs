// Запускатель helloytd.
//
// Python работает прямо внутри этого процесса (через runtime\python314.dll),
// поэтому в диспетчере задач и на панели задач программа видна как «helloytd»
// со своим значком, а не как pythonw.exe. Без аргументов открывает окно;
// с аргументами ведёт себя как python.exe — так кнопка «Обновить yt-dlp» вызывает pip.
using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

[assembly: AssemblyTitle("helloytd")]
[assembly: AssemblyProduct("helloytd")]
[assembly: AssemblyDescription("YouTube video and audio downloader")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

static class Launcher
{
    // Искать зависимости Python рядом с его DLL.
    const uint LoadWithAlteredSearchPath = 0x00000008;
    static readonly bool Russian = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "ru";

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr LoadLibraryExW(string path, IntPtr reserved, uint flags);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, ExactSpelling = true)]
    static extern IntPtr GetProcAddress(IntPtr module, string name);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate int PyMain(int argc, [MarshalAs(UnmanagedType.LPArray, ArraySubType = UnmanagedType.LPWStr)] string[] argv);

    // STA — как ждёт Qt: иначе не работают перетаскивание и буфер обмена.
    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string dll = Path.Combine(Path.Combine(root, "runtime"), "python314.dll");
        IntPtr python = LoadLibraryExW(dll, IntPtr.Zero, LoadWithAlteredSearchPath);
        if (python == IntPtr.Zero)
        {
            Fail(Russian
                ? "Не удалось загрузить runtime.\n\nРаспакуйте архив helloytd целиком: " + root
                : "Could not load the runtime.\n\nExtract the entire helloytd archive: " + root);
            return 1;
        }
        PyMain pyMain = (PyMain)Marshal.GetDelegateForFunctionPointer(
            GetProcAddress(python, "Py_Main"), typeof(PyMain));

        bool window = args.Length == 0;
        string[] argv = new string[(window ? 2 : args.Length) + 1];
        argv[0] = Assembly.GetExecutingAssembly().Location;
        if (window)
        {
            argv[1] = "-m";
            argv[2] = "app.main";
        }
        else
        {
            Array.Copy(args, 0, argv, 1, args.Length);
        }

        int code = pyMain(argv.Length, argv);
        if (window && code != 0)
        {
            Fail(Russian
                ? "helloytd завершился с ошибкой (код " + code + ").\n\nПодробности в data\\app.log."
                : "helloytd exited with error code " + code + ".\n\nSee data\\app.log for details.");
        }
        return code;
    }

    static void Fail(string message)
    {
        MessageBox.Show(message, "helloytd", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
