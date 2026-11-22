using System;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.VisualBasic;
using System.Runtime.InteropServices;

public static class ResearchCoachFolder {
    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("42f85136-db7e-439c-85f1-e4075d135fc8")]
    private interface FileDialog {
        [PreserveSig] int Show(IntPtr owner);
        void SetFileTypes(uint count, IntPtr types);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IntPtr folder);
        void SetFolder(IntPtr folder);
        void GetFolder(out IntPtr folder);
        void GetCurrentSelection(out IntPtr item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName(out IntPtr name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void GetResult(out ShellItem item);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")]
    private interface ShellItem {
        void BindToHandler(IntPtr ctx, ref Guid handler, ref Guid id, out IntPtr result);
        void GetParent(out ShellItem parent);
        void GetDisplayName(uint kind, out IntPtr name);
    }

    public static string Pick(string title) {
        var type = Type.GetTypeFromCLSID(new Guid("dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7"));
        var dialog = (FileDialog)Activator.CreateInstance(type);
        try {
            const uint pickFolders = 0x20, forceFileSystem = 0x40, pathMustExist = 0x800;
            uint options;
            dialog.GetOptions(out options);
            dialog.SetOptions(options | pickFolders | forceFileSystem | pathMustExist);
            dialog.SetTitle(title);
            int code = dialog.Show(IntPtr.Zero);
            if (code == unchecked((int)0x800704C7)) return null;
            Marshal.ThrowExceptionForHR(code);
            ShellItem item;
            dialog.GetResult(out item);
            try {
                const uint fileSystemPath = 0x80058000;
                IntPtr path;
                item.GetDisplayName(fileSystemPath, out path);
                try { return Marshal.PtrToStringUni(path); }
                finally { Marshal.FreeCoTaskMem(path); }
            } finally { Marshal.ReleaseComObject(item); }
        } finally { Marshal.ReleaseComObject(dialog); }
    }

    [STAThread]
    public static int Main(string[] args) {
        try {
            bool create = args.Length == 1 && args[0] == "new";
            string folder = Pick(create ? "选择新文件夹要放在哪里" : "选择课题文件夹");
            string name = null;
            if (folder != null && create) {
                name = Interaction.InputBox("输入新文件夹的名称", "新建课题文件夹", "");
                if (name.Length == 0) folder = null;
            }
            byte[] payload = Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(new { folder, name }));
            using (var output = Console.OpenStandardOutput()) {
                output.Write(payload, 0, payload.Length);
            }
            return 0;
        } catch (Exception error) {
            Console.Error.Write(error.Message);
            return 1;
        }
    }
}
