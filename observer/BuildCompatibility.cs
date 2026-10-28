// Generated from assets/game-builds.json; no arbitrary build override.
using System;
using System.IO;
using System.Security.Cryptography;
namespace SiNiSistarCompatibility;
internal static class BuildCompatibility
{
    static string Hash(string path){using var stream=File.OpenRead(path);return Convert.ToHexString(SHA256.Create().ComputeHash(stream)).ToLowerInvariant();}
    internal static bool Validate(string root,out string fingerprint,out string profile)
    {
        fingerprint=Hash(Path.Combine(root,"GameAssembly.dll"));
        var metadata=Hash(Path.Combine(root,"SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat"));
        if(fingerprint=="b869493305bbe587598c8709e7fe271f00d79d37803c6a8241946d6a6297499d" && metadata=="a56278d0162b6c148312b56fbe208b54ba9af2d3bad609ebf9349b7ae7ddc84b") {profile="full-1.3.1";return true;}
        if(fingerprint=="d8a9c09002dfb5cb834ab25bde2864bb4379d22e699cb249f79e78fd648c7383" && metadata=="76ad83efc7ee7fe67f468a298ed6de6be6c62dff5790dfa23ee4a5991b946d9b") {profile="steam-lite-1.3.1";return true;}
        profile="unsupported";return false;
    }
}
