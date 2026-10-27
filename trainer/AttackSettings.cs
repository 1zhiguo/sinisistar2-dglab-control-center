// GPL-3.0-only. Separate helper multiplier; never writes game upgrade data.
using System;
using System.IO;
using System.Text.Json;
using BepInEx.Configuration;

namespace SiNiSistarTrainer;

internal sealed class AttackSettings
{
    readonly ConfigFile config;
    readonly ConfigEntry<double> entry;
    public double Value=>entry.Value;

    public AttackSettings(ConfigFile config,string legacyLog)
    {
        this.config=config;
        config.SaveOnConfigSet=false;
        // Bind retains an existing config value. On the first upgrade only,
        // recover the latest successful explicit command from the old helper.
        entry=config.Bind("Gameplay","AttackMultiplier",PreviousValue(legacyLog),
            new ConfigDescription("Extra multiplier applied after the game's own attack upgrades. 1 preserves original damage. Saved across restarts.",new AcceptableValueRange<double>(0,10)));
        if(!double.IsFinite(entry.Value))throw new InvalidDataException("Invalid saved attack multiplier");
        config.Save();
    }

    public void Set(double value)
    {
        if(!double.IsFinite(value)||value<0||value>10)throw new ArgumentOutOfRangeException(nameof(value));
        double before=entry.Value;
        entry.Value=value;
        try{config.Save();}
        catch{entry.Value=before;throw;}
    }

    static double PreviousValue(string path)
    {
        if(!File.Exists(path))return 1;
        using var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
        bool partial=file.Length>262144;
        if(partial)file.Seek(-262144,SeekOrigin.End);
        using var reader=new StreamReader(file);
        if(partial)reader.ReadLine();
        double result=1;
        while(reader.ReadLine() is string line){
            try{
                using var document=JsonDocument.Parse(line);var row=document.RootElement;
                if(row.TryGetProperty("attribute",out var attribute)&&attribute.ValueKind==JsonValueKind.String&&attribute.GetString()=="attack"
                    &&row.TryGetProperty("ok",out var ok)&&ok.ValueKind==JsonValueKind.True
                    &&row.TryGetProperty("after",out var after)&&after.ValueKind==JsonValueKind.Number
                    &&after.TryGetDouble(out var value)&&double.IsFinite(value)&&value>=0&&value<=10)result=value;
            }catch(JsonException){ }
        }
        return result;
    }

    public static int Damage(int original,double factor)
    {
        if(factor==1.0||original<=0)return original;
        return (int)Math.Clamp(Math.Round(original*factor,MidpointRounding.AwayFromZero),0,1000000);
    }
}
