package com.roamsync.app.navigation

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

@Module @InstallIn(SingletonComponent::class) abstract class NavigationModule { @Binds abstract fun source(impl: AmapNavigationSource): NavigationSource }
