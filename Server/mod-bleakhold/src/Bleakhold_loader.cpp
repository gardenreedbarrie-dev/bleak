/*
 * mod-bleakhold: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

void AddBleakholdScripts();
void AddBleakholdCommandScripts();

// Called by the generated modules loader: "Add" + module folder name with '-' replaced by '_' + "Scripts".
void Addmod_bleakholdScripts()
{
    AddBleakholdScripts();
    AddBleakholdCommandScripts();
}
